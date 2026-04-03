# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from core.ai_features.registry import register_ai_feature


@register_ai_feature(
    'assignment_description',
    label='AI Grading Context',
    description='Auto-generates an AI summary of assignment requirements. Used as context by Suggested Comments, Submission Summary, and Comment Generation.',
)
def _feature():
    pass
