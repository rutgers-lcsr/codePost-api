# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from core.ai_features.registry import register_ai_feature


@register_ai_feature(
    'suggested_comments',
    label='Suggested Comments',
    description='File-level AI feedback suggestions shown to graders before they start reviewing',
    requires=['assignment_description'],
)
def _feature():
    pass
