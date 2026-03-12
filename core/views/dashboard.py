# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
"""
Dashboard ViewSet for platform admin statistics.
"""
import json

from rest_framework import viewsets, status
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.decorators import action
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema
from django.contrib.auth.models import User
from django.db.models import Count, Q
from django.utils import timezone
from datetime import timedelta

from core.models import Organization, Course, Assignment, Section
from core.serializers.dashboard import DashboardStatsSerializer, AssignmentDeadlineSerializer
from core.serializers.user import UserSerializer


class DashboardViewSet(viewsets.ViewSet):
    """
    Provides aggregated statistics for the platform admin dashboard.
    All endpoints require superuser permissions.
    """
    permission_classes = [IsAuthenticated, IsAdminUser]

    @extend_schema(responses={200: DashboardStatsSerializer})
    @action(detail=False, methods=['GET'])
    def stats(self, request):
        """
        Returns aggregated platform statistics.
        """
        # Organization stats
        total_organizations = Organization.objects.count()
        
        # Course stats
        total_courses = Course.objects.count()
        active_courses = Course.objects.filter(archived=False).count()
        archived_courses = Course.objects.filter(archived=True).count()
        
        # User stats - use annotations for efficiency
        total_users = User.objects.count()
        total_codepost_admins = User.objects.filter(is_superuser=True).count()
        
        # Active users (logged in within 30 days)
        thirty_days_ago = timezone.now() - timedelta(days=30)
        active_users = User.objects.filter(last_login__gte=thirty_days_ago).count()
        
        # Inactive users (never logged in or not in 90 days)
        ninety_days_ago = timezone.now() - timedelta(days=90)
        inactive_users = User.objects.filter(
            Q(last_login__isnull=True) | Q(last_login__lt=ninety_days_ago)
        ).count()
        
        # Role counts using annotations
        total_students = User.objects.filter(student_courses__isnull=False).distinct().count()
        total_graders = User.objects.filter(
            Q(grader_courses__isnull=False) | Q(superGrader_courses__isnull=False)
        ).distinct().count()
        total_course_admins = User.objects.filter(courseAdmin_courses__isnull=False).distinct().count()
        
        # Other stats
        total_sections = Section.objects.count()
        total_assignments = Assignment.objects.count()
        
        # Averages
        avg_courses_per_org = round(total_courses / max(total_organizations, 1), 1)
        avg_students_per_course = round(total_students / max(active_courses, 1), 1)
        
        return Response({
            'totalOrganizations': total_organizations,
            'totalCourses': total_courses,
            'activeCourses': active_courses,
            'archivedCourses': archived_courses,
            'totalUniqueUsers': total_users,
            'totalCodePostAdmins': total_codepost_admins,
            'totalCourseAdmins': total_course_admins,
            'totalGraders': total_graders,
            'totalStudents': total_students,
            'totalSections': total_sections,
            'totalAssignments': total_assignments,
            'avgCoursesPerOrg': avg_courses_per_org,
            'avgStudentsPerCourse': avg_students_per_course,
            'totalInactiveUsers': inactive_users,
            'activeUsers30d': active_users,
        })

    @extend_schema(responses={200: AssignmentDeadlineSerializer(many=True)})
    @action(detail=False, methods=['GET'])
    def deadlines(self, request):
        """
        Returns all assignments with their due dates and late upload deadlines.
        Useful for planning deployment windows.
        """
        assignments = (
            Assignment.objects
            .select_related('course')
            .filter(course__archived=False)
            .annotate(student_count=Count('course__students'))
            .order_by('uploadDueDate')
        )

        results = []
        for a in assignments:
            due = a.uploadDueDate
            late_deadline = None
            if due and a.allowLateUploads and a.maxLateDays > 0:
                late_deadline = due + timedelta(days=a.maxLateDays)

            results.append({
                'id': a.id,
                'name': a.name,
                'courseName': a.course.name,
                'coursePeriod': a.course.period,
                'courseId': a.course.id,
                'uploadDueDate': due,
                'lateUploadDeadline': late_deadline,
                'maxLateDays': a.maxLateDays,
                'allowLateUploads': a.allowLateUploads,
                'allowStudentUpload': a.allowStudentUpload,
                'regradeDeadline': a.regradeDeadline,
                'studentCount': a.student_count,
            })

        serializer = AssignmentDeadlineSerializer(results, many=True)
        return Response(serializer.data)

    @extend_schema(responses={200: UserSerializer(many=True)})
    @action(detail=False, methods=['GET'])
    def pending_admins(self, request):
        """
        Returns all users with pendingValidation=True across all organizations.
        Used by the SuperAdmin dashboard to manage pending admin requests.
        """
        pending_users = User.objects.filter(
            profile__pendingValidation=True
        ).select_related('profile', 'profile__organization').order_by('-profile__created')

        serializer = UserSerializer(pending_users, many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=False, methods=['POST'])
    def approve_pending_admin(self, request):
        """
        Approve a pending admin request (superuser only).
        Payload: { 'user_email': '...' }
        """
        from core.emails import NewAdminActivationEmail
        from log.models import Event as LogEvent

        email = request.data.get('user_email')
        if not email:
            return Response({'error': 'Missing user_email'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(email=email, profile__pendingValidation=True)
        except User.DoesNotExist:
            return Response({'error': 'Pending user not found'}, status=status.HTTP_404_NOT_FOUND)

        org = user.profile.organization

        user.profile.pendingValidation = False
        user.profile.canCreateCourses = True
        user.profile.canModifyRosters = True
        user.is_active = True
        user.save()
        user.profile.save()

        # Send activation email
        NewAdminActivationEmail(user=user).send_email(
            organization_name=org.name if org else "Unknown"
        )

        LogEvent.objects.create(
            category="registration",
            user=str(user),
            description="Admin approved by staff",
            meta=json.dumps({"approved_by": request.user.email}),
        )

        return Response({'status': 'approved'})

    @action(detail=False, methods=['POST'])
    def deny_pending_admin(self, request):
        """
        Deny a pending admin request (superuser only).
        Payload: { 'user_email': '...' }
        """
        from core.utils import is_course_member
        from log.models import Event as LogEvent

        email = request.data.get('user_email')
        if not email:
            return Response({'error': 'Missing user_email'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(email=email, profile__pendingValidation=True)
        except User.DoesNotExist:
            return Response({'error': 'Pending user not found'}, status=status.HTTP_404_NOT_FOUND)

        user.profile.pendingValidation = False
        user.profile.save()

        LogEvent.objects.create(
            category="registration",
            user=str(user),
            description="Admin denied by staff",
            meta=json.dumps({"denied_by": request.user.email}),
        )

        if not is_course_member(user):
            user.delete()
            return Response({'status': 'denied_and_deleted'})

        return Response({'status': 'denied'})
