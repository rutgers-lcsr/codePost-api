# This file is used for temporary utility endpoints

from rest_framework import status
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

from core.logging import logEvent
from core.permissions.helpers import isSuperGrader, returnNotAuthorized, returnForbidden
from core.auth import Authentications, type_of_auth
from core.models import Course

from util.slack import Slack

import json


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
             message=f"CIP activated by {user.email} for course {course.name}")
    return Response({'success': True}, status=status.HTTP_200_OK)
