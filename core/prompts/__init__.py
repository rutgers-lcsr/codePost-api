# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.

# Import all prompt modules to trigger registration with the prompt_registry.
# Each module uses the @register_prompt decorator, which runs at import time.
from core.prompts import (  # noqa: F401
    assignment_description,
    comment_generation,
    quiz_generation,
    submission_summary,
    suggested_comments,
    test_generation,
)
