# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
"""
AI Service for Comment Generation

Supports multiple AI providers through a unified interface:
- Google Gemini (default)
- OpenAI
- Ollama (self-hosted)
- Custom providers via Portkey

Usage:
    from core.services.ai_service import AIService
    
    service = AIService(course)
    result = service.generate_comment(
        selected_content="def foo():\n    pass",
        grader_draft="This function is incomplete",
        rubric_context="Missing implementation",
    )
"""

from __future__ import annotations

from encodings.base64_codec import base64_decode
import hashlib
import logging
import re
from decimal import Decimal
from typing import TYPE_CHECKING, Optional, Literal
from dataclasses import dataclass
from core.models import Course, Assignment, SubmissionFile, User

if TYPE_CHECKING:
    import pymupdf


# -----------------------------------------------------------------------
# Curated list of models per provider.
# Each entry: (model_id, display_label, is_default)
# -----------------------------------------------------------------------
AI_MODELS: dict[str, list[tuple[str, str, bool]]] = {
    'gemini': [
        ('gemini-3-pro-preview', 'Gemini 3 Pro (Preview)', True),
        ('gemini-2.5-flash', 'Gemini 2.5 Flash', True),
        ('gemini-2.5-pro', 'Gemini 2.5 Pro', False),
        ('gemini-2.0-flash', 'Gemini 2.0 Flash', False),
        ('gemini-1.5-flash', 'Gemini 1.5 Flash', False),
        ('gemini-1.5-pro', 'Gemini 1.5 Pro', False),
    ],
    'openai': [
        ('gpt-4o-mini', 'GPT-4o Mini', True),
        ('gpt-4o', 'GPT-4o', False),
        ('gpt-4.1', 'GPT-4.1', False),
        ('gpt-4.1-mini', 'GPT-4.1 Mini', False),
        ('gpt-4.1-nano', 'GPT-4.1 Nano', False),
        ('o3-mini', 'o3 Mini', False),
    ],
    'ollama': [
        ('llama3.2', 'Llama 3.2', True),
        ('llama3.1', 'Llama 3.1', False),
        ('mistral', 'Mistral', False),
        ('codellama', 'Code Llama', False),
        ('deepseek-coder-v2', 'DeepSeek Coder V2', False),
        ('qwen2.5-coder', 'Qwen 2.5 Coder', False),
        ('phi3', 'Phi-3', False),
    ],
    'portkey': [
        ('default', 'Default (gateway-configured)', True),
    ],
    'custom': [
        ('default', 'Default', True),
    ],
}

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------
# Provider model listing (queries the provider's API for available models)
# -----------------------------------------------------------------------

async def list_provider_models(
    provider: str,
    api_key: str = '',
    base_url: str = '',
) -> list[dict[str, str]]:
    """
    Query a provider's API for available models.
    Returns a list of dicts: [{'id': '...', 'name': '...'}]
    Raises on network/auth errors.
    """
    if provider == 'gemini':
        return await _list_gemini_models(api_key)
    elif provider == 'openai':
        return await _list_openai_models(api_key)
    elif provider == 'ollama':
        return await _list_ollama_models(base_url)
    elif provider == 'portkey':
        return await _list_portkey_models(api_key, base_url)
    return []


async def _list_gemini_models(api_key: str) -> list[dict[str, str]]:
    """List models from Google Gemini API."""
    from google import genai
    client = genai.Client(api_key=api_key)
    models = []
    pager = await client.aio.models.list()
    async for m in pager:
        model_id = m.name or ''
        # The API returns "models/gemini-2.5-flash" — strip the prefix
        if model_id.startswith('models/'):
            model_id = model_id[len('models/'):]
        display_name = m.display_name or model_id
        # Only include generative models (skip embedding/retrieval models)
        if hasattr(m, 'supported_generation_methods') and m.supported_generation_methods:  # type: ignore[attr-defined]  # google-generativeai Model
            if 'generateContent' not in m.supported_generation_methods:  # type: ignore[operator]  # google-generativeai Model type
                continue
        models.append({'id': model_id, 'name': display_name})
    return models


async def _list_openai_models(api_key: str) -> list[dict[str, str]]:
    """List models from OpenAI API."""
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=api_key)
    response = await client.models.list()
    models = []
    for m in response.data:
        models.append({'id': m.id, 'name': m.id})
    # Sort alphabetically
    models.sort(key=lambda x: x['id'])
    return models


async def _list_ollama_models(base_url: str) -> list[dict[str, str]]:
    """List locally installed models from Ollama."""
    import httpx
    url = (base_url or 'http://localhost:11434').rstrip('/')
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{url}/api/tags", timeout=10.0)
        response.raise_for_status()
        data = response.json()
    models = []
    for m in data.get('models', []):
        model_name = m.get('name', '')
        # Strip ":latest" suffix for cleaner display
        display = model_name.replace(':latest', '') if model_name.endswith(':latest') else model_name
        models.append({'id': model_name, 'name': display})
    return models


async def _list_portkey_models(api_key: str, base_url: str) -> list[dict[str, str]]:
    """List models from Portkey gateway (OpenAI-compatible /v1/models)."""
    import httpx
    url = (base_url or 'https://api.portkey.ai/v1').rstrip('/')
    if url.endswith('/v1'):
        endpoint = f"{url}/models"
    else:
        endpoint = f"{url}/v1/models"

    headers: dict[str, str] = {}
    if api_key:
        headers['x-portkey-api-key'] = api_key

    async with httpx.AsyncClient() as client:
        response = await client.get(endpoint, headers=headers, timeout=10.0)
        response.raise_for_status()
        data = response.json()
    models = []
    for m in data.get('data', []):
        model_id = m.get('id', '')
        models.append({'id': model_id, 'name': model_id})
    models.sort(key=lambda x: x['id'])
    return models


@dataclass
class GenerationContext:
    """Context for AI comment generation."""
    selected_content: str  # The selected lines/cell
    grader_draft: str = ""  # Grader's draft text to improve
    rubric_context: str = ""  # Rubric comment info if linked
    file_content: str = ""  # Entire file (for 'file' context level)
    all_files_content: str = ""  # All submission + assignment files (for 'all_files' level)
    assignment_name: str = ""
    file_name: str = ""


@dataclass 
class GenerationResult:
    """Result from AI comment generation."""
    text: str
    success: bool
    error: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cached_tokens: int = 0


class AIService:
    """
    AI service for generating grading comments.
    Supports multiple providers through a unified interface.
    """
    # This is to ensure the ai response is consistently in markdown format
    GLOBAL_SYSTEM_PROMPT =""""""
    
    DEFAULT_SYSTEM_PROMPT = """You are an AI assistant helping grade student code submissions.
Your task is to generate clear, constructive feedback for students.

Guidelines:
- Be specific about what the issue is
- Explain why it matters
- Suggest how to fix it when appropriate
- Be encouraging but honest
- Keep comments concise (1-3 sentences)

Context:
- Assignment: {assignment_name}
- File: {file_name}
- File Content:
{file_content}
"""

    def __init__(self, course: Course, assignment: Optional[Assignment] = None):
        self.course = course
        self.assignment = assignment

        # Resolve effective AI config: course-own settings or org-level
        if course.ai_use_own_settings and course.ai_provider:
            # Course explicitly uses its own key
            self.provider = course.ai_provider
            self.api_key = course.ai_api_key
            self.base_url = course.ai_base_url
            self.model = course.ai_model or self._get_default_model()
        elif not course.ai_use_own_settings and course.organization:
            # Try to inherit from org
            org = course.organization
            if (
                org.ai_provider
                and (org.ai_api_key or org.ai_provider in ('ollama', 'portkey'))
                and not org.ai_disabled
                and self._org_allows_course(org, course)
            ):
                self.provider = org.ai_provider
                self.api_key = org.ai_api_key
                self.base_url = org.ai_base_url
                self.model = org.ai_model or self._get_default_model_for(org.ai_provider)
            else:
                # Org not available, fall back to course fields (may be empty)
                self.provider = course.ai_provider
                self.api_key = course.ai_api_key
                self.base_url = course.ai_base_url
                self.model = course.ai_model or self._get_default_model()
        else:
            # Default: use course fields (ai_use_own_settings=True but no provider,
            # or no organization attached)
            self.provider = course.ai_provider
            self.api_key = course.ai_api_key
            self.base_url = course.ai_base_url
            self.model = course.ai_model or self._get_default_model()

    @staticmethod
    def _org_allows_course(org, course: Course) -> bool:
        """Check if the org's course policy allows this course to use the org AI key."""
        if org.ai_course_policy == 'all':
            return True
        if org.ai_course_policy == 'selected':
            return org.ai_enabled_courses.filter(pk=course.pk).exists()
        return False

    def _get_default_model_for(self, provider: str) -> str:
        """Get default model for a given provider string."""
        models = AI_MODELS.get(provider, [])
        for model_id, _, is_default in models:
            if is_default:
                return model_id
        return 'default'
        
    def _get_default_model(self) -> str:
        """Get default model for the configured provider."""
        return self._get_default_model_for(self.provider)
    
    @property
    def is_configured(self) -> bool:
        """Check if AI is properly configured for this course."""
        if self.provider in ('ollama', 'portkey'):
            # Ollama and Portkey (self-hosted) only need provider + base_url
            return bool(self.provider and self.base_url)
        return bool(self.provider and self.api_key)

    # ------------------------------------------------------------------
    # Cost estimation & usage recording
    # ------------------------------------------------------------------

    # TTL (in seconds) for Gemini explicit context caches
    GEMINI_CACHE_TTL = 300  # 5 minutes

    # Provider-specific discount on cached input tokens (fraction of full input rate)
    # Gemini: cached tokens billed at 25% of full input price (75% discount)
    # OpenAI: cached tokens billed at 50% of full input price (50% discount)
    CACHED_TOKEN_RATE: dict[str, float] = {
        'gemini': 0.25,
        'openai': 0.50,
    }

    # Rates: (input $/1M tokens, output $/1M tokens)
    TOKEN_RATES: dict[str, tuple[float, float]] = {
        # Gemini
        'gemini-3-pro-preview': (2.00, 12.00),
        'gemini-2.5-flash': (0.15, 0.60),
        'gemini-2.5-pro': (1.25, 10.00),
        'gemini-2.0-flash': (0.10, 0.40),
        'gemini-1.5-flash': (0.075, 0.30),
        'gemini-1.5-pro': (1.25, 5.00),
        # OpenAI
        'gpt-4o': (2.50, 10.00),
        'gpt-4o-mini': (0.15, 0.60),
        'gpt-4.1': (2.00, 8.00),
        'gpt-4.1-mini': (0.40, 1.60),
        'gpt-4.1-nano': (0.10, 0.40),
        'o3-mini': (1.10, 4.40),
    }

    @staticmethod
    def estimate_cost(provider: str, model: str, input_tokens: int, output_tokens: int,
                      custom_rates: dict | None = None,
                      cached_tokens: int = 0) -> float:
        """
        Estimate the cost of an AI API call in USD.

        Rate lookup order:
          1. ``custom_rates`` dict  (org/course overrides merged by caller)
          2. ``TOKEN_RATES``        (hardcoded defaults)
          3. Falls back to 0.0 for unknown models / self-hosted providers.

        ``custom_rates`` format: ``{"model-name": {"input": 0.15, "output": 0.60}, ...}``

        When ``cached_tokens`` > 0, the cached portion of input tokens is billed
        at the provider's discounted rate (see ``CACHED_TOKEN_RATE``).
        """
        rates = None
        if custom_rates and model in custom_rates:
            r = custom_rates[model]
            if isinstance(r, dict) and 'input' in r and 'output' in r:
                rates = (float(r['input']), float(r['output']))
        if not rates:
            rates = AIService.TOKEN_RATES.get(model)
        if not rates:
            return 0.0
        # Split input tokens into non-cached and cached portions
        effective_cached = min(cached_tokens, input_tokens)
        non_cached_input = input_tokens - effective_cached
        cache_discount = AIService.CACHED_TOKEN_RATE.get(provider, 1.0)
        input_cost = (non_cached_input / 1_000_000) * rates[0]
        cached_cost = (effective_cached / 1_000_000) * rates[0] * cache_discount
        output_cost = (output_tokens / 1_000_000) * rates[1]
        return float(Decimal(str(input_cost + cached_cost + output_cost)).quantize(Decimal('0.000001')))

    def _get_merged_rates(self) -> dict | None:
        """Merge custom token rates: course overrides org overrides."""
        rates: dict = {}
        org = self.course.organization if self.course else None
        if org and org.ai_token_rates:
            rates.update(org.ai_token_rates)
        if self.course and self.course.ai_token_rates:
            rates.update(self.course.ai_token_rates)
        return rates or None

    def record_usage(
        self,
        result: 'GenerationResult',
        user: User,
        request_type: str = 'comment_generation',
    ) -> None:
        """
        Persist an AIUsageRecord for the generation that just completed.

        Parameters
        ----------
        result : GenerationResult
            The result returned by ``generate_comment`` or ``generate_test_script``.
        user : User
            The Django user who triggered the generation.
        request_type : str
            One of ``'comment_generation'``, ``'test_generation'``, ``'code_review'``, etc.
        """
        try:
            from core.models import AIUsageRecord

            AIUsageRecord.objects.create(
                organization=self.course.organization,
                course=self.course,
                assignment=self.assignment,
                user=user,
                provider=self.provider or '',
                model=self.model or '',
                request_type=request_type,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                total_tokens=result.total_tokens,
                cached_tokens=result.cached_tokens,
                estimated_cost=self.estimate_cost(
                    self.provider or '', self.model or '',
                    result.input_tokens, result.output_tokens,
                    custom_rates=self._get_merged_rates(),
                    cached_tokens=result.cached_tokens,
                ),
                status='success' if result.success else 'error',
                error_message=result.error if not result.success else None,
            )
        except Exception as e:
            logger.warning(f"Failed to record AI usage: {e}")

    def get_system_prompt(self, context: GenerationContext) -> str:
        """Build the system prompt with context."""
        if self.assignment and self.assignment.ai_system_prompt:
            template = self.assignment.ai_system_prompt
        else:
            template = self.DEFAULT_SYSTEM_PROMPT
            
        try:
            return "\n\n".join([
                template.format(
                assignment_name=context.assignment_name,
                file_name=context.file_name,
                file_content=context.file_content,
                selected_content=context.selected_content,
                rubric_context=context.rubric_context,
                grader_draft=context.grader_draft,
                all_files=context.all_files_content,
            ),
            self.GLOBAL_SYSTEM_PROMPT
        ])
        except Exception as e:
            # Fallback if the user's template contains invalid placeholders or syntax
            logger.warning(f"Failed to format system prompt template: {e}")
            return "\n\n".join([
                template,
                self.GLOBAL_SYSTEM_PROMPT
            ])
    
    def build_user_prompt(self, context: GenerationContext, system_prompt_template: str = "") -> str:
        """
        Build the user prompt for generation.
        Checks system_prompt_template to avoid duplicating content already in system prompt.
        """
        parts = []
        
        # Selected code (only if not in system prompt)
        if '{selected_content}' not in system_prompt_template:
            parts.append(f"**Selected Code:**\n```\n{context.selected_content}\n```")
        
        # Grader's draft (only if not in system prompt)
        if '{grader_draft}' not in system_prompt_template:
            if context.grader_draft:
                parts.append(f"**Grader's Draft Comment:**\n{context.grader_draft}")
                parts.append("\nPlease improve and expand on this draft comment.")
            else:
                parts.append("\nPlease write a feedback comment for this code.")
        else:
            # If draft is in system prompt, we still need a "trigger" instruction in user prompt?
            # Or assume system prompt has instructions.
            # We'll add a generic instruction if the draft logic is handled in system prompt.
            if not parts: # If nothing else added yet
                 parts.append("\nPlease generate the feedback comment.")

        # Rubric context (only if not in system prompt)
        if '{rubric_context}' not in system_prompt_template and context.rubric_context:
            parts.append(f"\n**Rubric Context:**\n{context.rubric_context}")
            
        return "\n\n".join(parts)
    
    async def generate_comment(
        self,
        context: GenerationContext,
    ) -> GenerationResult:
        """
        Generate a comment using the configured AI provider.
        
        Args:
            context: GenerationContext with all relevant information
            
        Returns:
            GenerationResult with generated text or error
        """
        if not self.is_configured:
            return GenerationResult(
                text="",
                success=False,
                error="AI is not configured for this course"
            )
        
        try:
            # Check if context was already included in system prompt
            system_prompt_template = self.assignment.ai_system_prompt if self.assignment and self.assignment.ai_system_prompt else self.DEFAULT_SYSTEM_PROMPT

            system_prompt = self.get_system_prompt(context)
            user_prompt = self.build_user_prompt(context, system_prompt_template)

            # Call the appropriate provider
            if self.provider == 'gemini':
                logger.debug(f"Calling Gemini ({self.model}) with system prompt: {system_prompt}\nUser prompt: {user_prompt}")
                text, input_tokens, output_tokens, total_tokens, cached_tokens = await self._call_gemini(system_prompt, user_prompt)
            elif self.provider == 'openai':
                logger.debug(f"Calling OpenAI ({self.model}) with system prompt: {system_prompt}\nUser prompt: {user_prompt}")
                text, input_tokens, output_tokens, total_tokens, cached_tokens = await self._call_openai(system_prompt, user_prompt)
            elif self.provider == 'ollama':
                logger.debug(f"Calling Ollama ({self.model}) with system prompt: {system_prompt}\nUser prompt: {user_prompt}")
                text, input_tokens, output_tokens, total_tokens, cached_tokens = await self._call_ollama(system_prompt, user_prompt)
            elif self.provider in ('portkey', 'custom'):
                logger.debug(f"Calling Portkey/Custom ({self.model}) with system prompt: {system_prompt}\nUser prompt: {user_prompt}")
                text, input_tokens, output_tokens, total_tokens, cached_tokens = await self._call_portkey(system_prompt, user_prompt)
            else:
                raise ValueError(f"Unknown AI provider: {self.provider}")

            return GenerationResult(
                text=text,
                success=True,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                cached_tokens=cached_tokens,
            )

        except Exception as e:
            error_msg = self._parse_error(e)
            logger.error(f"AI generation failed: {e}", exc_info=True)
            return GenerationResult(
                text="",
                success=False,
                error=error_msg
            )

    LANGUAGE_EXAMPLES: dict[str, str] = {
        "python": """@test("Test Name", points=10, description="Test Description")
def test_name():
    assert func() == expected

@test("Test Partial", points=10, description="Partial credit example")
def test_partial():
    return 10 if func() == expected else 5

@test("Test Explanation", points=10, description="Score + explanation")
def test_explanation():
    score = 10 if func() == expected else 0
    return score, f"Computed score: {score}"
""",
        "java": """@Test(name="Test Name", points=10, description="Test Description")
public double testName() {
    assertEquals(expected, func());
    return 10.0;
}

@Test(name="Test Partial", points=10, description="Partial credit example")
public double testPartial() {
    return func() == expected ? 10.0 : 5.0;
}

@Test(name="Test Explanation", points=10, description="Score + explanation")
public Object[] testExplanation() {
    double score = (func() == expected) ? 10.0 : 0.0;
    return new Object[] { score, "This test returns score and explanation" };
}""",
        "cpp": """TEST_DESC(TestName, 10, "Test Description") {
    assertTrue(func() == expected, "Expected func() to equal expected");
}

TEST_DESC(TestPartial, 10, "Partial credit example") {
    double score = (func() == expected) ? 10.0 : 5.0;
    return score;
}

TEST_DESC_TIMEOUT(TestExplanation, 10, "Score + explanation", 30) {
    double score = (func() == expected) ? 10.0 : 0.0;
    return return_score(score, "This test returns score and explanation");
}""",
        "c": """TEST_DESC(TestName, 10, "Test Description") {
    assertTrue(func() == expected, "Expected func() to equal expected");
}

TEST_DESC(TestPartial, 10, "Partial credit example") {
    double score = (func() == expected) ? 10.0 : 5.0;
    return score;
}

TEST_DESC_TIMEOUT(TestExplanation, 10, "Score + explanation", 30) {
    double score = (func() == expected) ? 10.0 : 0.0;
    return return_score(score, "This test returns score and explanation");
}""",
        "javascript": """test("Test Name", 10, "Test Description", function() {
    if (func() !== expected) {
        throw new Error("Expected " + expected);
    }
});

test("Test Partial", 10, "Partial credit example", function() {
    return func() === expected ? 10 : 5;
});

test("Test Explanation", 10, "Score + explanation", function() {
    const score = func() === expected ? 10 : 0;
    return [score, "This test returns score and explanation"];
}, 30);
""",
        "node": """test("Test Name", 10, "Test Description", function() {
    if (func() !== expected) {
        throw new Error("Expected " + expected);
    }
});

test("Test Partial", 10, "Partial credit example", function() {
    return func() === expected ? 10 : 5;
});

test("Test Explanation", 10, "Score + explanation", function() {
    const score = func() === expected ? 10 : 0;
    return [score, "This test returns score and explanation"];
}, 30);
""",
        "php": """Tester::test("Test Name", 10.0, "Test Description", function() {
    if (func() !== expected) {
        throw new Exception("Expected " . expected);
    }
});

Tester::test("Test Partial", 10.0, "Partial credit example", function() {
    return (func() === expected) ? 10.0 : 5.0;
});

Tester::test("Test Explanation", 10.0, "Score + explanation", function() {
    $score = (func() === expected) ? 10.0 : 0.0;
    return [$score, "This test returns score and explanation"];
}, 30);
""",
        "r": """run_test("Test Name", 10, "Test Description", function() {
    if (func() != expected) {
        stop(paste("Expected", expected))
    }
})

run_test("Test Partial", 10, "Partial credit example", function() {
    return(ifelse(func() == expected, 10, 5))
})

run_test("Test Explanation", 10, "Score + explanation", function() {
    score <- ifelse(func() == expected, 10, 0)
    return(list(score, "This test returns score and explanation"))
}, 30)
""",
        "ruby": """run_test("Test Name", 10, "Test Description") do
    result = func()
    raise "Expected #{expected}" unless result == expected
end

run_test("Test Partial", 10, "Partial credit example") do
    (func() == expected) ? 10 : 5
end

run_test("Test Explanation", 10, "Score + explanation", 30) do
    score = (func() == expected) ? 10 : 0
    [score, "This test returns score and explanation"]
end"""
    }

    TEST_GENERATION_PROMPT = """You are an expert autograder for a Computer Science course.
Your task is to generate a robust test script for a student submission file: {target_filename}.
The test script should verify the correctness of the student's code based on the provided context.

CRITICAL RULES:
1. You MUST use the exact testing harness pattern provided in the example below.
2. Do NOT import ANY external testing libraries (like unittest, pytest, RSpec, JUnit, etc.).
3. Do NOT define your own `TestCase` classes or custom runner logic. Use the provided top-level functions or macros ONLY.
4. Do NOT attempt to parse, read, or import the student submission file (e.g., do not parse JSON or use nbformat/json libraries).
5. ASSUME all student functions and classes are ALREADY LOADED and available in the global scope. Call them directly.
6. If the example uses `@test`, use `@test`. If it uses `Tester::test`, use `Tester::test`. If it uses `run_test`, use `run_test`.
7. Return ONLY the code for the test script. No markdown formatting, no explanations.
8. For Java tests, methods annotated with @Test must NOT be void. Return a score (number) or an Object[] of [score, explanation].
9. For Java in this environment: output ONLY `@Test` methods. Do NOT include `package` declarations, `import` statements, or wrapper classes (e.g., `class StudentTests` or `class TestRunner`).

Context:
- Context File (Solution/Spec): {context_filename}
{context_content}

Target File to Test: {target_filename}
Target Content:
{target_code}

Language: {language}

Language-Specific Test Harness Example ({language}):
{language_example}

Based on the context (logic to test) and the example harness above, generate the test script.
"""

    def _extract_java_test_methods(self, text: str) -> list[str]:
        """Extract @Test-annotated Java methods, preserving method bodies."""
        methods: list[str] = []

        for match in re.finditer(r'@Test\s*\([^)]*\)', text, flags=re.DOTALL):
            start = match.start()
            body_start = text.find('{', match.end())
            if body_start == -1:
                continue

            depth = 0
            end = -1
            for i in range(body_start, len(text)):
                ch = text[i]
                if ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        end = i
                        break

            if end != -1:
                methods.append(text[start:end + 1].strip())

        return methods

    def _normalize_generated_test_script(self, text: str, language: str) -> str:
        """Normalize model output to match runtime harness expectations."""
        normalized = text.strip()

        # Strip markdown fences if present.
        if normalized.startswith("```"):
            lines = normalized.split('\n')
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            normalized = "\n".join(lines).strip()

        # Java script harness (TestRunner.java) expects method bodies only.
        if language == 'java':
            methods = self._extract_java_test_methods(normalized)
            if methods:
                return "\n\n".join(methods)

            # Fallback cleanup if extraction fails.
            cleaned_lines = []
            for line in normalized.splitlines():
                stripped = line.strip()
                if stripped.startswith('package '):
                    continue
                if stripped.startswith('import '):
                    continue
                cleaned_lines.append(line)
            return "\n".join(cleaned_lines).strip()

        return normalized

    async def generate_test_script(
        self,
        context_file_content: str,
        context_filename: str,
        target_filename: str,
        target_code: str = "",
        language: str = "python",
        rubric_text: str = ""
    ) -> GenerationResult:
        """
        Generate a test script using the configured AI provider.
        """
        if not self.is_configured:
            return GenerationResult(
                text="",
                success=False,
                error="AI is not configured for this course"
            )

        try:
            # Select appropriate example or fallback to python
            lang_key = language.lower()
            if lang_key not in self.LANGUAGE_EXAMPLES:
                # Try to map common aliases
                if lang_key in ['py']:
                    lang_key = 'python'
                elif lang_key in ['js']:
                    lang_key = 'javascript'
                elif lang_key in ['nodejs']:
                    lang_key = 'node'
                elif lang_key in ['c++']:
                    lang_key = 'cpp'

            example = self.LANGUAGE_EXAMPLES.get(lang_key, self.LANGUAGE_EXAMPLES['python'])

            # Ensure target_code is never None
            safe_target_code = target_code if target_code else "(No content available)"

            # Format rubric section
            rubric_section = ""
            if rubric_text:
                rubric_section = f"Rubric Criterion (Test Goal):\n{rubric_text}\n"

            system_prompt = self.TEST_GENERATION_PROMPT.format(
                context_filename=context_filename,
                context_content=context_file_content,
                target_filename=target_filename,
                target_code=safe_target_code,
                language=language,
                language_example=example
            )

            if rubric_section:
                system_prompt += f"\n\n{rubric_section}"

            user_prompt = f"Generate a {language} test script for {target_filename}."

            # Call the appropriate provider
            if self.provider == 'gemini':
                text, input_tokens, output_tokens, total_tokens, cached_tokens = await self._call_gemini(system_prompt, user_prompt)
            elif self.provider == 'openai':
                text, input_tokens, output_tokens, total_tokens, cached_tokens = await self._call_openai(system_prompt, user_prompt)
            elif self.provider == 'ollama':
                text, input_tokens, output_tokens, total_tokens, cached_tokens = await self._call_ollama(system_prompt, user_prompt)
            elif self.provider in ('portkey', 'custom'):
                text, input_tokens, output_tokens, total_tokens, cached_tokens = await self._call_portkey(system_prompt, user_prompt)
            else:
                raise ValueError(f"Unknown AI provider: {self.provider}")

            text = self._normalize_generated_test_script(text, lang_key)

            return GenerationResult(
                text=text,
                success=True,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                cached_tokens=cached_tokens,
            )

        except Exception as e:
            error_msg = self._parse_error(e)
            logger.error(f"AI test generation failed: {e}", exc_info=True)
            return GenerationResult(
                text="",
                success=False,
                error=error_msg
            )

    def _parse_error(self, e: Exception) -> str:
        """Parse exception into user-friendly error message."""
        error_str = str(e).lower()
        
        # API key errors
        if 'api_key' in error_str or 'api key' in error_str or 'invalid' in error_str and 'key' in error_str:
            return "Invalid API key. Please check your AI configuration in Course Settings."
        
        # Rate limiting
        if 'rate' in error_str and 'limit' in error_str:
            return "Rate limit exceeded. Please wait a moment and try again."
        
        if 'quota' in error_str or '429' in error_str:
            return "API quota exceeded. Please check your API usage limits."
        
        # Authentication errors
        if 'unauthorized' in error_str or '401' in error_str:
            return "Authentication failed. Please verify your API key."
        
        # Connection errors
        if 'connection' in error_str or 'timeout' in error_str:
            return "Failed to connect to AI service. Please try again later."
        
        # Model not found
        if 'model' in error_str and ('not found' in error_str or 'invalid' in error_str):
            return f"Model '{self.model}' not found. Please check your AI configuration."
        
        # Content policy
        if 'safety' in error_str or 'blocked' in error_str or 'content' in error_str and 'policy' in error_str:
            return "Content was blocked by AI safety filters. Please try a different selection."
        
        # Generic fallback with shortened message
        short_msg = str(e)[:200]
        if len(str(e)) > 200:
            short_msg += "..."
        return f"AI generation failed: {short_msg}"
    
    async def _get_or_create_gemini_cache(self, system_prompt: str) -> str | None:
        """
        Get or create a Gemini explicit context cache for the system prompt.
        Returns the cache name if successful, None otherwise (falls back to uncached).
        """
        from django.core.cache import cache as django_cache
        from google import genai
        from google.genai import types

        prompt_hash = hashlib.sha256(
            f"{self.model}\n{system_prompt}".encode()
        ).hexdigest()[:16]
        cache_key = f"gemini_ctx:{prompt_hash}"

        # Check Django cache for an existing Gemini cache reference
        cache_name = django_cache.get(cache_key)
        if cache_name:
            return cache_name

        # Create a new explicit cached content on Gemini's servers
        try:
            client = genai.Client(api_key=self.api_key)
            cached = await client.aio.caches.create(
                model=self.model,
                config=types.CreateCachedContentConfig(
                    system_instruction=system_prompt,
                    ttl=f"{self.GEMINI_CACHE_TTL}s",
                ),
            )
            # Store reference with a slightly shorter TTL to avoid stale refs
            django_cache.set(cache_key, cached.name, timeout=self.GEMINI_CACHE_TTL - 30)
            logger.debug(f"Created Gemini cache: {cached.name} for prompt hash {prompt_hash}")
            return cached.name
        except Exception as e:
            # Explicit caching can fail (e.g., prompt too short, unsupported model).
            # Fall back to implicit caching (Gemini 2.5+ does this automatically).
            logger.debug(f"Gemini explicit cache creation skipped: {e}")
            return None

    async def _call_gemini(self, system_prompt: str, user_prompt: str) -> tuple[str, int, int, int, int]:
        """Call Google Gemini API. Returns (text, input_tokens, output_tokens, total_tokens, cached_tokens)."""
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=self.api_key)

        # Try explicit context caching for the system prompt
        cache_name = await self._get_or_create_gemini_cache(system_prompt)

        if cache_name:
            config = types.GenerateContentConfig(
                cached_content=cache_name,
            )
        else:
            config = types.GenerateContentConfig(
                system_instruction=system_prompt,
            )

        response = await client.aio.models.generate_content(
            model=self.model,
            contents=user_prompt,
            config=config,
        )
        input_tokens = getattr(response.usage_metadata, 'prompt_token_count', 0) or 0
        output_tokens = getattr(response.usage_metadata, 'candidates_token_count', 0) or 0
        total_tokens = getattr(response.usage_metadata, 'total_token_count', 0) or (input_tokens + output_tokens)
        cached_tokens = getattr(response.usage_metadata, 'cached_content_token_count', 0) or 0
        return response.text or "", input_tokens, output_tokens, total_tokens, cached_tokens
    
    async def _call_openai(self, system_prompt: str, user_prompt: str) -> tuple[str, int, int, int, int]:
        """Call OpenAI API. Returns (text, input_tokens, output_tokens, total_tokens, cached_tokens)."""
        from openai import AsyncOpenAI
        
        client = AsyncOpenAI(api_key=self.api_key)
        response = await client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        usage = response.usage
        input_tokens = usage.prompt_tokens if usage else 0
        output_tokens = usage.completion_tokens if usage else 0
        total_tokens = usage.total_tokens if usage else (input_tokens + output_tokens)
        # OpenAI automatically caches prompts >1024 tokens; extract cached count
        cached_tokens = 0
        if usage and hasattr(usage, 'prompt_tokens_details') and usage.prompt_tokens_details:
            cached_tokens = getattr(usage.prompt_tokens_details, 'cached_tokens', 0) or 0
        return response.choices[0].message.content or "", input_tokens, output_tokens, total_tokens, cached_tokens
    
    async def _call_ollama(self, system_prompt: str, user_prompt: str) -> tuple[str, int, int, int, int]:
        """Call Ollama API (self-hosted). Returns (text, input_tokens, output_tokens, total_tokens, cached_tokens)."""
        import httpx
        
        base_url = self.base_url or "http://localhost:11434"
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{base_url}/api/generate",
                json={
                    "model": self.model,
                    "system": system_prompt,
                    "prompt": user_prompt,
                    "stream": False,
                },
                timeout=60.0,
            )
            response.raise_for_status()
            data = response.json()
            input_tokens = data.get('prompt_eval_count', 0) or 0
            output_tokens = data.get('eval_count', 0) or 0
            return data["response"], input_tokens, output_tokens, input_tokens + output_tokens, 0
    
    async def _call_portkey(self, system_prompt: str, user_prompt: str) -> tuple[str, int, int, int, int]:
        """Call Portkey AI gateway (self-hosted or cloud). Returns (text, input_tokens, output_tokens, total_tokens, cached_tokens).
        
        Portkey is an AI Gateway that proxies requests to underlying providers.
        When self-hosted, it typically only needs a base URL (API key is optional).
        Uses x-portkey-api-key header for gateway auth, not Authorization.
        The endpoint is OpenAI-compatible: POST /v1/chat/completions.
        """
        import httpx
        
        base_url = (self.base_url or "https://api.portkey.ai/v1").rstrip('/')
        # Ensure the URL doesn't already end with /v1 when we append the path
        if base_url.endswith('/v1'):
            url = f"{base_url}/chat/completions"
        else:
            url = f"{base_url}/v1/chat/completions"

        headers: dict[str, str] = {
            "Content-Type": "application/json",
        }
        # API key is optional for self-hosted Portkey gateways
        if self.api_key:
            headers["x-portkey-api-key"] = self.api_key

        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                headers=headers,
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                },
                timeout=60.0,
            )
            response.raise_for_status()
            data = response.json()
            usage = data.get('usage', {})
            input_tokens = usage.get('prompt_tokens', 0) or 0
            output_tokens = usage.get('completion_tokens', 0) or 0
            total_tokens = usage.get('total_tokens', 0) or (input_tokens + output_tokens)
            return data["choices"][0]["message"]["content"], input_tokens, output_tokens, total_tokens, 0

    # ------------------------------------------------------------------
    # Streaming chat with tool calling
    # ------------------------------------------------------------------

    CHAT_SYSTEM_PROMPT = """You are an AI grading assistant embedded in the codePost code review console.
You are helping a grader review a student's code submission.

**Your capabilities:**
- Read and analyze the student's submitted files
- View autograder test results
- Create inline comments on specific lines of code
- Apply rubric comments from the assignment rubric
- Navigate the grader to specific files and lines

**Important rules:**
- ALWAYS explain what you want to do before calling a tool
- Be specific about line numbers and file names
- When suggesting a comment, explain your reasoning first
- Keep feedback constructive and educational
- If you're unsure, ask the grader for clarification

**Character-level precision (code/text files only):**
For regular code and text files, prefer using start_char and end_char to highlight the specific
expression, variable, or token the feedback is about, rather than highlighting the full line.
- start_char is the 0-indexed character offset from the beginning of start_line.
- end_char is the 0-indexed character offset from the beginning of end_line.
- Example: to highlight `foo` in `x = foo + bar` (where `foo` starts at position 4 and ends at 7),
  set start_char=4 and end_char=7.
- If the feedback applies to an entire line or block, you may omit start_char and end_char.
- Do NOT use start_char/end_char for notebook (.ipynb) or PDF files.

**Notebook (.ipynb) files:**
For Jupyter notebook files, line numbers work differently:
- start_line and end_line are **0-indexed cell indices**, NOT line numbers within a cell.
- Cell 1 in the UI corresponds to index 0, Cell 2 to index 1, etc.
- When using read_file_contents on a notebook, the output will label each cell with its index.
- To comment on a specific cell, set start_line to that cell's index (e.g., for Cell 3, use start_line=2).
- Comments on notebooks target entire cells — you cannot target a specific line within a cell.

**Context:**
- Assignment: {assignment_name}
- Submission ID: {submission_id}
- Files: {file_list}
{rubric_context}
{existing_comments}
{test_summary}
"""

    SUMMARIZE_PROMPT = (
        "Summarize the following grading conversation concisely. "
        "Preserve: key decisions made, comments added, rubric items applied, "
        "pending issues, and any grading strategy discussed. "
        "Be brief — this summary will be used as context for continuing the conversation."
    )

    # Threshold for automatic summarization (message count)
    SUMMARIZE_THRESHOLD = 20

    async def chat_stream(
        self,
        messages: list[dict[str, str]],
        tools: list[dict] | None = None,
    ):
        """
        Stream a chat response with tool-calling support.

        Yields dicts:
          {"type": "token", "content": "..."}          — text delta
          {"type": "tool_call", "name": "...", "args": {...}, "id": "..."}  — tool request
          {"type": "done", "input_tokens": N, "output_tokens": N}          — completion
          {"type": "error", "message": "..."}           — error

        The caller is responsible for:
          1. Handling tool calls (executing or asking user approval).
          2. Re-invoking chat_stream with the tool result appended to messages.
        """
        if not self.is_configured:
            yield {"type": "error", "message": "AI is not configured for this course."}
            return

        try:
            if self.provider == 'gemini':
                async for chunk in self._stream_gemini(messages, tools):
                    yield chunk
            elif self.provider == 'openai':
                async for chunk in self._stream_openai(messages, tools):
                    yield chunk
            elif self.provider == 'ollama':
                async for chunk in self._stream_ollama(messages, tools):
                    yield chunk
            elif self.provider in ('portkey', 'custom'):
                async for chunk in self._stream_openai_compat(messages, tools):
                    yield chunk
            else:
                yield {"type": "error", "message": f"Unknown AI provider: {self.provider}"}
        except Exception as e:
            error_msg = self._parse_error(e)
            logger.error(f"Chat stream failed: {e}", exc_info=True)
            yield {"type": "error", "message": error_msg}

    async def summarize_conversation(self, messages: list[dict[str, str]]) -> str:
        """Summarize a conversation into a compact paragraph for context window management."""
        conversation_text = "\n".join(
            f"[{m['role']}]: {m['content'][:500]}" for m in messages if m.get('content')
        )
        prompt = f"{self.SUMMARIZE_PROMPT}\n\n{conversation_text}"

        try:
            if self.provider == 'gemini':
                text, *_ = await self._call_gemini(self.SUMMARIZE_PROMPT, conversation_text)
            elif self.provider == 'openai':
                text, *_ = await self._call_openai(self.SUMMARIZE_PROMPT, conversation_text)
            elif self.provider == 'ollama':
                text, *_ = await self._call_ollama(self.SUMMARIZE_PROMPT, conversation_text)
            elif self.provider in ('portkey', 'custom'):
                text, *_ = await self._call_portkey(self.SUMMARIZE_PROMPT, conversation_text)
            else:
                return ""
            return text.strip()
        except Exception as e:
            logger.warning(f"Conversation summarization failed: {e}")
            return ""

    def build_chat_system_prompt(
        self,
        assignment_name: str,
        submission_id: int,
        file_list: str,
        rubric_context: str = "",
        existing_comments: str = "",
        test_summary: str = "",
    ) -> str:
        """Build the system prompt for chat, filling in context."""
        return self.CHAT_SYSTEM_PROMPT.format(
            assignment_name=assignment_name,
            submission_id=submission_id,
            file_list=file_list,
            rubric_context=f"- Rubric:\n{rubric_context}" if rubric_context else "",
            existing_comments=f"- Existing comments:\n{existing_comments}" if existing_comments else "",
            test_summary=f"- Test results:\n{test_summary}" if test_summary else "",
        )

    # ------------------------------------------------------------------
    # Provider-specific streaming implementations
    # ------------------------------------------------------------------

    async def _stream_openai(self, messages: list[dict[str, str]], tools: list[dict] | None):
        """Stream from OpenAI with tool calling."""
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=self.api_key)
        kwargs: dict = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        collected_tool_calls: dict[int, dict] = {}
        input_tokens = 0
        output_tokens = 0
        cached_tokens = 0

        stream = await client.chat.completions.create(**kwargs)
        async for chunk in stream:
            if chunk.usage:
                input_tokens = chunk.usage.prompt_tokens or 0
                output_tokens = chunk.usage.completion_tokens or 0
                if hasattr(chunk.usage, 'prompt_tokens_details') and chunk.usage.prompt_tokens_details:
                    cached_tokens = getattr(chunk.usage.prompt_tokens_details, 'cached_tokens', 0) or 0

            for choice in (chunk.choices or []):
                delta = choice.delta
                if delta.content:
                    yield {"type": "token", "content": delta.content}

                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in collected_tool_calls:
                            collected_tool_calls[idx] = {
                                "id": tc.id or "",
                                "name": "",
                                "args_str": "",
                            }
                        if tc.function:
                            if tc.function.name:
                                collected_tool_calls[idx]["name"] = tc.function.name
                            if tc.function.arguments:
                                collected_tool_calls[idx]["args_str"] += tc.function.arguments

                if choice.finish_reason == "tool_calls":
                    import json
                    for _idx, tc_data in sorted(collected_tool_calls.items()):
                        try:
                            args = json.loads(tc_data["args_str"]) if tc_data["args_str"] else {}
                        except json.JSONDecodeError:
                            args = {}
                        yield {
                            "type": "tool_call",
                            "id": tc_data["id"],
                            "name": tc_data["name"],
                            "args": args,
                        }
                    return  # Pause for tool execution

        yield {"type": "done", "input_tokens": input_tokens, "output_tokens": output_tokens, "cached_tokens": cached_tokens}

    async def _stream_gemini(self, messages: list[dict[str, str]], tools: list[dict] | None):
        """Stream from Google Gemini with tool calling."""
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=self.api_key)

        # Convert OpenAI-format messages to Gemini format
        system_instruction = None
        contents: list = []
        for msg in messages:
            role = msg["role"]
            if role == "system":
                system_instruction = msg["content"]
            elif role == "user":
                contents.append(types.Content(role="user", parts=[types.Part.from_text(text=msg["content"])]))
            elif role == "assistant":
                contents.append(types.Content(role="model", parts=[types.Part.from_text(text=msg["content"])]))
            elif role == "tool":
                contents.append(types.Content(role="user", parts=[types.Part.from_text(text=f"[Tool Result]: {msg['content']}")]))

        # Convert OpenAI tool schemas to Gemini tool declarations
        gemini_tools = None
        if tools:
            declarations = []
            for t in tools:
                func = t.get("function", {})
                declarations.append(types.FunctionDeclaration(
                    name=func["name"],
                    description=func.get("description", ""),
                    parameters=func.get("parameters"),
                ))
            gemini_tools = [types.Tool(function_declarations=declarations)]

        # Try explicit context caching for the system instruction
        cache_name = None
        if system_instruction:
            cache_name = await self._get_or_create_gemini_cache(system_instruction)

        if cache_name:
            config = types.GenerateContentConfig(
                cached_content=cache_name,
                tools=gemini_tools,
                thinking_config=types.ThinkingConfig(thinking_budget=8000) if (self.model or '').startswith('gemini-2.5') else None,
            )
        else:
            config = types.GenerateContentConfig(
                system_instruction=system_instruction,
                tools=gemini_tools,
                thinking_config=types.ThinkingConfig(thinking_budget=8000) if (self.model or '').startswith('gemini-2.5') else None,
            )

        full_text = ""
        input_tokens = 0
        output_tokens = 0
        cached_tokens = 0
        is_thinking = False

        async for chunk in await client.aio.models.generate_content_stream(
            model=self.model,
            contents=contents,
            config=config,
        ):
            if chunk.usage_metadata:
                input_tokens = getattr(chunk.usage_metadata, 'prompt_token_count', 0) or 0
                output_tokens = getattr(chunk.usage_metadata, 'candidates_token_count', 0) or 0
                cached_tokens = getattr(chunk.usage_metadata, 'cached_content_token_count', 0) or 0

            if chunk.candidates:
                for candidate in chunk.candidates:
                    if candidate.content and candidate.content.parts:
                        for part in candidate.content.parts:
                            # Thought tokens (Gemini 2.5 thinking mode) — signal UI but don't emit as content
                            if getattr(part, 'thought', False):
                                if not is_thinking:
                                    is_thinking = True
                                    yield {"type": "thinking"}
                                continue
                            if is_thinking and part.text:
                                is_thinking = False
                                yield {"type": "thinking_done"}
                            if part.text:
                                yield {"type": "token", "content": part.text}
                                full_text += part.text
                            if part.function_call:
                                fc = part.function_call
                                yield {
                                    "type": "tool_call",
                                    "id": fc.name,
                                    "name": fc.name,
                                    "args": dict(fc.args) if fc.args else {},
                                }
                                return  # Pause for tool execution

        yield {"type": "done", "input_tokens": input_tokens, "output_tokens": output_tokens, "cached_tokens": cached_tokens}

    async def _stream_ollama(self, messages: list[dict[str, str]], tools: list[dict] | None):
        """Stream from Ollama (local). Tool calling via /api/chat endpoint."""
        import httpx
        import json

        base_url = (self.base_url or "http://localhost:11434").rstrip("/")
        payload: dict = {
            "model": self.model,
            "messages": messages,
            "stream": True,
        }
        if tools:
            payload["tools"] = tools

        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream("POST", f"{base_url}/api/chat", json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    msg = data.get("message", {})

                    # Tool calls
                    if msg.get("tool_calls"):
                        for tc in msg["tool_calls"]:
                            func = tc.get("function", {})
                            yield {
                                "type": "tool_call",
                                "id": func.get("name", ""),
                                "name": func.get("name", ""),
                                "args": func.get("arguments", {}),
                            }
                        return

                    # Text content
                    content = msg.get("content", "")
                    if content:
                        yield {"type": "token", "content": content}

                    if data.get("done"):
                        yield {
                            "type": "done",
                            "input_tokens": data.get("prompt_eval_count", 0) or 0,
                            "output_tokens": data.get("eval_count", 0) or 0,
                            "cached_tokens": 0,
                        }
                        return

    async def _stream_openai_compat(self, messages: list[dict[str, str]], tools: list[dict] | None):
        """Stream from Portkey/Custom (OpenAI-compatible). Reuses the OpenAI streaming logic."""
        import httpx
        import json

        base_url = (self.base_url or "https://api.portkey.ai/v1").rstrip("/")
        if base_url.endswith("/v1"):
            url = f"{base_url}/chat/completions"
        else:
            url = f"{base_url}/v1/chat/completions"

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.api_key:
            headers["x-portkey-api-key"] = self.api_key

        payload: dict = {
            "model": self.model,
            "messages": messages,
            "stream": True,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        collected_tool_calls: dict[int, dict] = {}
        input_tokens = 0
        output_tokens = 0

        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str.strip() == "[DONE]":
                        break
                    try:
                        data = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    if "usage" in data and data["usage"]:
                        input_tokens = data["usage"].get("prompt_tokens", 0) or 0
                        output_tokens = data["usage"].get("completion_tokens", 0) or 0

                    for choice in data.get("choices", []):
                        delta = choice.get("delta", {})
                        if delta.get("content"):
                            yield {"type": "token", "content": delta["content"]}

                        for tc in delta.get("tool_calls", []):
                            idx = tc.get("index", 0)
                            if idx not in collected_tool_calls:
                                collected_tool_calls[idx] = {"id": tc.get("id", ""), "name": "", "args_str": ""}
                            func = tc.get("function", {})
                            if func.get("name"):
                                collected_tool_calls[idx]["name"] = func["name"]
                            if func.get("arguments"):
                                collected_tool_calls[idx]["args_str"] += func["arguments"]

                        if choice.get("finish_reason") == "tool_calls":
                            for _idx, tc_data in sorted(collected_tool_calls.items()):
                                try:
                                    args = json.loads(tc_data["args_str"]) if tc_data["args_str"] else {}
                                except json.JSONDecodeError:
                                    args = {}
                                yield {"type": "tool_call", "id": tc_data["id"], "name": tc_data["name"], "args": args}
                            return

        yield {"type": "done", "input_tokens": input_tokens, "output_tokens": output_tokens, "cached_tokens": 0}


REGION_COMMENT_MARKER = 1_000_000


def _extract_pdf_selection(
    doc: pymupdf.Document,
    selected_pages: list[int],
    start_char: int | None,
    end_char: int | None,
) -> str:
    """Extract text from a PDF based on the comment selection type.
    
    Handles three modes:
    - Region selection (start_char >= 1,000,000): decodes bounding box percentages
      and extracts text from that rectangular area on the page.
    - Text selection (start_char/end_char provided): extracts the full page as
      markdown (character offsets from the browser text layer may not match pymupdf).
    - Page-level (no char info): extracts the full selected pages as markdown.
    """
    import pymupdf
    import pymupdf4llm as pdf_utils

    has_chars = start_char is not None and end_char is not None

    # Region-based selection: decode bounding box and extract text from that area
    if has_chars and start_char is not None and end_char is not None and start_char >= REGION_COMMENT_MARKER and end_char >= REGION_COMMENT_MARKER:
        s = start_char - REGION_COMMENT_MARKER
        e = end_char - REGION_COMMENT_MARKER
        left_pct = s // 101
        top_pct = s % 101
        right_pct = e // 101
        bottom_pct = e % 101

        parts = []
        for page_idx in selected_pages:
            if page_idx < 0 or page_idx >= len(doc):
                continue
            page = doc[page_idx]
            rect = page.rect
            clip = pymupdf.Rect(
                rect.x0 + (left_pct / 100) * rect.width,
                rect.y0 + (top_pct / 100) * rect.height,
                rect.x0 + (right_pct / 100) * rect.width,
                rect.y0 + (bottom_pct / 100) * rect.height,
            )
            text = page.get_textbox(clip).strip()
            if text:
                parts.append(text)

        if parts:
            return "\n\n".join(parts)
        # Fall through to full-page extraction if region extraction yielded nothing
        # (e.g. scanned PDF without OCR)

    # Text selection or page-level: extract full selected pages as markdown
    return str(pdf_utils.to_markdown(doc, pages=selected_pages))


def build_context_from_file(
    file: SubmissionFile,
    start_line: int,
    end_line: int,
    start_char: int | None = None,
    end_char: int | None = None,
) -> GenerationContext:
    """
    Build generation context from a submission file.
    
    Args:
        file: The SubmissionFile being commented on
        start_line: Start line of selection (0-indexed). For notebooks, this is the cell index.
                    For PDFs, this is the 1-based page number.
        end_line: End line of selection (0-indexed). For notebooks, this is the cell index.
                  For PDFs, this is the 1-based page number.
        start_char: Optional character offset or encoded region start (for PDFs).
        end_char: Optional character offset or encoded region end (for PDFs).
        
    Returns:
        GenerationContext with populated fields
    """
    submission = file.submission
    assignment = submission.assignment
    
    # Handle notebooks specially
    if file.name.endswith('.ipynb'):
        import json
        try:
            notebook = json.loads(file.data)
            cells = notebook.get('cells', [])
            
            # Get selected cells
            selected_parts = []
            # Bound the indices (treating inputs as 0-based indices)
            start_idx = max(0, min(start_line, len(cells) - 1)) if cells else 0
            end_idx = max(0, min(end_line, len(cells) - 1)) if cells else 0
            
            for i in range(start_idx, end_idx + 1):
                cell = cells[i]
                cell_type = cell.get('cell_type', 'code')
                content = _parse_notebook_cell(cell, include_outputs=True)
                selected_parts.append(f"[{cell_type.upper()} CELL]\n{content}")
            
            selected_content = "\n\n".join(selected_parts)
            
            # Helper for full file content
            def get_notebook_markdown():
                parts = []
                for i, cell in enumerate(cells):
                    cell_type = cell.get('cell_type', 'code')
                    content = _parse_notebook_cell(cell, include_outputs=True)
                    parts.append(f"## Cell {i} ({cell_type})\n{content}")
                return "\n\n".join(parts)
                
            file_content_markdown = get_notebook_markdown()
            
        except json.JSONDecodeError:
             # Fallback to treating as text if json parse fails
             selected_content = "Error: Could not parse notebook content."
             file_content_markdown = file.data
    elif file.name.endswith('.pdf'):
        import pymupdf
        import pymupdf4llm as pdf_utils
        
        prefix = "data:application/pdf;base64,"
        if file.data.startswith(prefix):
            try:
                base64_data = file.data[len(prefix):]
                pdf_bytes, _ = base64_decode(base64_data.encode())  # Validate base64
            except Exception:
                selected_content = "Error: Could not decode PDF content."
                pdf_bytes = b""
        else: 
            pdf_bytes = file.data
        
        # Frontend sends 1-based page numbers as start_line/end_line for PDFs.
        # pymupdf4llm.to_markdown accepts 0-based page numbers via the `pages` param.
        selected_pages = list(range(start_line - 1, end_line))  # convert 1-based to 0-based
        
        stream = pdf_bytes if isinstance(pdf_bytes, bytes) else pdf_bytes.encode()
        doc = pymupdf.open(stream=stream, filetype="pdf")
        
        # Try to extract precise selection based on start_char/end_char
        selected_content = _extract_pdf_selection(
            doc, selected_pages, start_char, end_char
        )
        
        # Convert entire PDF to markdown for full file content
        file_content_markdown = str(pdf_utils.to_markdown(doc))
        doc.close()
    else:
        # Standard text file handling
        lines = file.data.split('\n')
        # Bound the indices (treating inputs as 0-based indices)
        start_idx = max(0, min(start_line, len(lines) - 1)) if lines else 0
        end_idx = max(0, min(end_line, len(lines) - 1)) if lines else 0
        
        selected_lines = lines[start_idx:end_idx + 1]
        
        # Narrow to character offsets within the selected lines if provided.
        # start_char/end_char are 0-indexed offsets within their respective lines.
        if start_char is not None and selected_lines:
            selected_lines[0] = selected_lines[0][start_char:]
        if end_char is not None and selected_lines:
            selected_lines[-1] = selected_lines[-1][:end_char]
        
        selected_content = '\n'.join(selected_lines)
        file_content_markdown = file.data

    context = GenerationContext(
        selected_content=selected_content,
        assignment_name=assignment.name,
        file_name=file.name,
    )
    
    # Determine if we need full file content or all files content
    system_prompt_template = assignment.ai_system_prompt if assignment.ai_system_prompt else AIService.DEFAULT_SYSTEM_PROMPT
    needs_file_content = '{file_content}' in system_prompt_template
    needs_all_files = '{all_files}' in system_prompt_template
    
    # Always include file content if needed
    if needs_file_content:
        context.file_content = file_content_markdown
        
    # Always include all files content (lazy loaded effectively since we just do queries here)
    if needs_all_files:
        other_files = []
        
        # Include other submission files
        for sub_file in submission.files.exclude(id=file.id):
            # If other file is notebook, maybe just skipped or simplified?
            # For now treating as raw data to save complexity, unless requested
            content_snippet = sub_file.data[:10000] + "..." if len(sub_file.data) > 10000 else sub_file.data
            other_files.append(f"**{sub_file.name}:**\n```\n{content_snippet}\n```")
            
        # Include assignment files
        for assign_file in assignment.files.all():
            other_files.append(f"**[Assignment File] {assign_file.name}:**\n```\n{assign_file.data}\n```")
            
        context.all_files_content = '\n\n'.join(other_files)
    
    return context


def _parse_notebook_cell(cell, include_outputs=False) -> str:
    """Parse a notebook cell to extract content and optionally outputs. These are nbformat v4 cells."""
    source = cell.get('source', [])
    content = ""
    if isinstance(source, list):
        content = "".join(source)
    else:
        content = str(source)
    
    if include_outputs and cell.get('cell_type') == 'code':
        outputs = cell.get('outputs', [])
        output_text = []
        for output in outputs:
            # Handle stream output (stdout/stderr)
            if output.get('output_type') == 'stream':
                text = output.get('text', [])
                if isinstance(text, list):
                    output_text.append("".join(text))
                else:
                    output_text.append(str(text))
            # Handle execute_result or display_data
            elif output.get('output_type') in ('execute_result', 'display_data'):
                data = output.get('data', {})
                # Prefer plain text representation
                if 'text/plain' in data:
                    text = data['text/plain']
                    if isinstance(text, list):
                        output_text.append("".join(text))
                    else:
                        output_text.append(str(text))
                elif 'text/html' in data:
                    output_text.append("[HTML Output]")
                elif 'image/png' in data:
                    output_text.append("[Image Output]")
            # Handle errors
            elif output.get('output_type') == 'error':
                ename = output.get('ename', '')
                evalue = output.get('evalue', '')
                output_text.append(f"Error: {ename}: {evalue}")

        if output_text:
            content += "\n\n[OUTPUT]:\n" + "\n".join(output_text)
    
    return content
