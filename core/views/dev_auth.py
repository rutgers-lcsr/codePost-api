# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from rest_framework.views import APIView
from rest_framework.response import Response
from django.contrib.auth.models import User
from core.serializers.user import UserSerializer
from core.views.auth import tokens_for_user
from django.conf import settings
from rest_framework import status

class LoginAsRoleView(APIView):
    """
    Auto-login as a specific role for development purposes.
    Only available when DEBUG=True.
    """
    permission_classes = [] 

    def post(self, request, *args, **kwargs):
        if not settings.DEBUG:
            return Response({"error": "Not allowed in production"}, status=status.HTTP_403_FORBIDDEN)

        role = request.data.get('role')
        user = None

        if role == 'student':
            user = User.objects.filter(username='student_only').first()
            if not user:
                # Fallback: Find a user who is a student but NOT admin/grader/superuser
                user = User.objects.filter(
                    student_courses__isnull=False,
                    grader_courses__isnull=True,
                    courseAdmin_courses__isnull=True,
                    is_superuser=False,
                    is_staff=False
                ).distinct().first()
        elif role == 'grader_basic':
            user = User.objects.filter(username='grader_basic').first()
            if not user:
                 # Grader but NOT rubric or super
                user = User.objects.filter(
                    grader_courses__isnull=False,
                    rubricEditor_courses__isnull=True,
                    superGrader_courses__isnull=True,
                    courseAdmin_courses__isnull=True,
                    is_superuser=False
                ).distinct().first()
        elif role == 'grader_rubric':
            user = User.objects.filter(username='grader_rubric').first()
            if not user:
                 # Rubric Editor but NOT super
                user = User.objects.filter(
                    rubricEditor_courses__isnull=False,
                    superGrader_courses__isnull=True,
                    courseAdmin_courses__isnull=True,
                    is_superuser=False
                ).distinct().first()
        elif role == 'grader_super':
            user = User.objects.filter(username='grader_super').first()
            if not user:
                # Super Grader
                user = User.objects.filter(
                    superGrader_courses__isnull=False,
                    courseAdmin_courses__isnull=True,
                    is_superuser=False
                ).distinct().first()
        elif role == 'course_admin':
            user = User.objects.filter(username='course_admin_only').first()
            if not user:
                user = User.objects.filter(courseAdmin_courses__isnull=False, is_superuser=False).distinct().first()
        elif role == 'staff':
            user = User.objects.filter(is_superuser=True).first()
        else:
            return Response({"error": "Invalid role. Options: student, grader_basic, grader_rubric, grader_super, course_admin, staff"}, status=status.HTTP_400_BAD_REQUEST)

        if not user:
             return Response({"error": f"No user found for role '{role}'. ensure database is populated."}, status=status.HTTP_404_NOT_FOUND)

        # We need to set request.user temporarily for serializer context to work properly if it checks permissions
        request.user = user

        # Generate an access + refresh pair and return the same packet as login
        access, refresh = tokens_for_user(user)

        serializer = UserSerializer(user, context={'request': request})
        data = serializer.data
        data['token'] = access
        data['refresh'] = refresh

        return Response(data)
