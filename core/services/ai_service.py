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

import logging
from typing import Optional, Literal
from dataclasses import dataclass
from core.models import Course, Assignment, SubmissionFile

logger = logging.getLogger(__name__)


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
        self.provider = course.ai_provider
        self.api_key = course.ai_api_key
        self.base_url = course.ai_base_url
        self.model = course.ai_model or self._get_default_model()
        
    def _get_default_model(self) -> str:
        """Get default model for the configured provider."""
        defaults = {
            'gemini': 'gemini-2.5-flash',
            'openai': 'gpt-4o-mini',
            'ollama': 'llama3.2',
            'custom': 'default',
        }
        return defaults.get(self.provider, 'default')
    
    @property
    def is_configured(self) -> bool:
        """Check if AI is properly configured for this course."""
        return bool(self.provider and self.api_key)
    
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
                logger.info(f"Calling Gemini with system prompt: {system_prompt}\nUser prompt: {user_prompt}")
                text = await self._call_gemini(system_prompt, user_prompt)
            elif self.provider == 'openai':
                text = await self._call_openai(system_prompt, user_prompt)
            elif self.provider == 'ollama':
                text = await self._call_ollama(system_prompt, user_prompt)
            else:
                text = await self._call_portkey(system_prompt, user_prompt)
                
            return GenerationResult(text=text, success=True)
            
        except Exception as e:
            error_msg = self._parse_error(e)
            logger.error(f"AI generation failed: {e}", exc_info=True)
            return GenerationResult(
                text="",
                success=False,
                error=error_msg
            )
    
    LANGUAGE_EXAMPLES = {
        "python": """@test("Test Name", points=10)
def test_function():
    assert func() == expected""",
        "java": """@Test(name="Test Name", points=10)
public void testFunction() {
    assertEquals(expected, func());
}""",
        "cpp": """TEST("Test Name", 10) {
    ASSERT_EQ(expected, func());
}""",
        "c": """TEST("Test Name", 10) {
    // Uses GoogleTest-style macros via wrapper
    ASSERT_EQ(expected, func());
}""",
        "javascript": """test("Test Name", 10, function() {
    if (func() !== expected) {
        throw new Error("Expected " + expected);
    }
});""",
        "node": """test("Test Name", 10, function() {
    if (func() !== expected) {
        throw new Error("Expected " + expected);
    }
});""",
        "php": """Tester::test("Test Name", 10.0, function() {
    if (func() !== expected) {
        throw new Exception("Expected " + expected);
    }
});""",
        "r": """run_test("Test Name", 10.0, function() {
    if (func() != expected) {
        stop("Expected " + expected)
    }
})""",
        "ruby": """run_test("Test Name", 10) do
    result = func()
    raise "Expected #{expected}" unless result == expected
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
6. If the example uses `@test`, use `@test`. If it uses `Tester::test`, use `Tester::test`.
7. Return ONLY the code for the test script. No markdown formatting, no explanations.

Context:
- Context File (Solution/Spec): {context_filename}
{context_content}

Target File to Test: {target_filename}
Language: {language}

Language-Specific Test Harness Example ({language}):
{language_example}

Based on the context (logic to test) and the example harness above, generate the test script.
"""

    async def generate_test_script(
        self,
        context_file_content: str,
        context_filename: str,
        target_filename: str,
        language: str = "python"
    ) -> GenerationResult:
        """
        Generate a test script using the configured AI provider.
        
        Args:
            context_file_content: Content of the solution/spec file.
            context_filename: Name of the solution/spec file.
            target_filename: Name of the student file to test.
            language: Target language.
            
        Returns:
            GenerationResult with generated script.
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
                if lang_key in ['py']: lang_key = 'python'
                elif lang_key in ['js', 'node']: lang_key = 'javascript'
                elif lang_key in ['c++']: lang_key = 'cpp'
            
            example = self.LANGUAGE_EXAMPLES.get(lang_key, self.LANGUAGE_EXAMPLES['python'])

            system_prompt = self.TEST_GENERATION_PROMPT.format(
                context_filename=context_filename,
                context_content=context_file_content,
                target_filename=target_filename,
                language=language,
                language_example=example
            )
            
            user_prompt = f"Generate a {language} test script for {target_filename}."
            
            # Call the appropriate provider
            if self.provider == 'gemini':
                text = await self._call_gemini(system_prompt, user_prompt)
            elif self.provider == 'openai':
                text = await self._call_openai(system_prompt, user_prompt)
            elif self.provider == 'ollama':
                text = await self._call_ollama(system_prompt, user_prompt)
            else:
                text = await self._call_portkey(system_prompt, user_prompt)
                
            # Strip markdown code blocks if present
            text = text.strip()
            if text.startswith("```"):
                lines = text.split('\n')
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines[-1].startswith("```"):
                    lines = lines[:-1]
                text = "\n".join(lines)
                
            return GenerationResult(text=text, success=True)
            
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
    
    async def _call_gemini(self, system_prompt: str, user_prompt: str) -> str:
        """Call Google Gemini API using the new google.genai package."""
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=self.api_key)
        
        response = await client.aio.models.generate_content(
            model=self.model,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
            ),
        )
        return response.text
    
    async def _call_openai(self, system_prompt: str, user_prompt: str) -> str:
        """Call OpenAI API."""
        from openai import AsyncOpenAI
        
        client = AsyncOpenAI(api_key=self.api_key)
        response = await client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return response.choices[0].message.content
    
    async def _call_ollama(self, system_prompt: str, user_prompt: str) -> str:
        """Call Ollama API (self-hosted)."""
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
            return response.json()["response"]
    
    async def _call_portkey(self, system_prompt: str, user_prompt: str) -> str:
        """Call custom provider via Portkey gateway."""
        import httpx
        
        base_url = self.base_url or "https://api.portkey.ai/v1"
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
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
            return response.json()["choices"][0]["message"]["content"]


def build_context_from_file(
    file: SubmissionFile,
    start_line: int,
    end_line: int,
) -> GenerationContext:
    """
    Build generation context from a submission file.
    
    Args:
        file: The SubmissionFile being commented on
        start_line: Start line of selection (0-indexed). For notebooks, this is the cell index.
        end_line: End line of selection (0-indexed). For notebooks, this is the cell index.
        
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
    else:
        # Standard text file handling
        lines = file.data.split('\n')
        # Bound the indices (treating inputs as 0-based indices)
        start_idx = max(0, min(start_line, len(lines) - 1)) if lines else 0
        end_idx = max(0, min(end_line, len(lines) - 1)) if lines else 0
        
        selected_lines = lines[start_idx:end_idx + 1]
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
