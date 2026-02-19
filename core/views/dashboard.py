"""
Dashboard ViewSet for platform admin statistics.
"""
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.decorators import action
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema
from django.contrib.auth.models import User
from django.db.models import Count, Q
from django.utils import timezone
from datetime import timedelta

from core.models import Organization, Course, Assignment, Section
from core.serializers.dashboard import DashboardStatsSerializer


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
