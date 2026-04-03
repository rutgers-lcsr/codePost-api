# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from core.ai_features.registry import register_ai_feature


@register_ai_feature(
    'comment_generation',
    label='Comment Generation',
    description='Inline AI comment generation in the code console ("Generate with AI" button)',    requires=['assignment_description'],)
def _feature():
    pass
