# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from core.ai_features.registry import register_ai_feature


@register_ai_feature(
    'quiz_generation',
    label='Quiz Question Suggestions',
    description='Suggest quiz questions from an assignment and course material. Instructors review and '
                'accept suggestions before they become real, editable quiz questions.',
    default_enabled=True,
)
def _feature():
    pass
