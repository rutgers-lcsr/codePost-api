# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from rest_framework import serializers


class DashboardStatsSerializer(serializers.Serializer):
    totalOrganizations = serializers.IntegerField()
    totalCourses = serializers.IntegerField()
    activeCourses = serializers.IntegerField()
    archivedCourses = serializers.IntegerField()
    totalUniqueUsers = serializers.IntegerField()
    totalCodePostAdmins = serializers.IntegerField()
    totalCourseAdmins = serializers.IntegerField()
    totalGraders = serializers.IntegerField()
    totalStudents = serializers.IntegerField()
    totalSections = serializers.IntegerField()
    totalAssignments = serializers.IntegerField()
    avgCoursesPerOrg = serializers.FloatField()
    avgStudentsPerCourse = serializers.FloatField()
    totalInactiveUsers = serializers.IntegerField()
    activeUsers30d = serializers.IntegerField()
