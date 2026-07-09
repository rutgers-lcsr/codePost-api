# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial Licensed, included with this software.
from core.ai_features.registry import register_ai_feature


@register_ai_feature(
    'personalized_quiz_generation',
    label='AI-Generated Quiz Questions',
    description="Generate quiz questions per student when they submit — the instructor's prompt "
                "can draw on the assignment and/or the student's own submission. Staff review and "
                "approve each student's questions before their quiz opens. Runs automatically on "
                'submission, so it is off by default.',
    default_enabled=False,
)
def _feature():
    pass
