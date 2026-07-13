# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.

# Import all feature modules to trigger registration with the ai_feature_registry.
from core.ai_features import (  # noqa: F401
    assignment_description,
    comment_generation,
    personalized_quiz_generation,
    quiz_generation,
    submission_summary,
    suggested_comments,
    test_generation,
)
