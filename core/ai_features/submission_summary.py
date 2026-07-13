# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from core.ai_features.registry import register_ai_feature


@register_ai_feature(
    'submission_summary',
    label='Submission Summary',
    description='AI-generated overview of a submission shown at the top of the grading panel',    requires=['assignment_description'],)
def _feature():
    pass
