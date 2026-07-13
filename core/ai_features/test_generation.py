# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from core.ai_features.registry import register_ai_feature


@register_ai_feature(
    'test_generation',
    label='Test Generation',
    description='AI-generated test scripts for the autograder',
)
def _feature():
    pass
