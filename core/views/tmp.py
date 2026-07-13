# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
# This file is used for temporary utility endpoints

import logging
logger = logging.getLogger("django")
from rest_framework import status
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema

from core.logging import logEvent
from core.permissions.helpers import returnForbidden
from core.models import Course
from core.serializers.tmp import ActivateCipResponseSerializer



@extend_schema(
    request=None,
    responses={200: ActivateCipResponseSerializer}
)
@api_view(['POST'])
@permission_classes((IsAuthenticated,))
def activate_cip(request):
    """

    """
    user = request.user

    if not user.is_superuser:
        return returnForbidden()

    code_in_place_course = 925  # code in place
    course = Course.objects.get(id=code_in_place_course)

    for grader in course.graders.all():
        if not grader.is_active:
            grader.is_active = True
            grader.save()

    for student in course.students.all():
        if not student.is_active:
            student.is_active = True
            student.save()
    logEvent("CIP Activation",
             message=f"CIP activated by {user.email} for course {course.name}",
             event_type='audit')
    return Response({'success': True}, status=status.HTTP_200_OK)
