# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
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


class AssignmentDeadlineSerializer(serializers.Serializer):
    """Serializer for assignment deadline data used by the deploy calendar."""
    id = serializers.IntegerField()
    name = serializers.CharField()
    courseName = serializers.CharField()
    coursePeriod = serializers.CharField()
    courseId = serializers.IntegerField()
    uploadDueDate = serializers.DateTimeField(allow_null=True)
    lateUploadDeadline = serializers.DateTimeField(allow_null=True)
    maxLateDays = serializers.IntegerField()
    allowLateUploads = serializers.BooleanField()
    allowStudentUpload = serializers.BooleanField()
    regradeDeadline = serializers.DateTimeField(allow_null=True)
    studentCount = serializers.IntegerField()


class AutogradingLanguageUsageSerializer(serializers.Serializer):
    language = serializers.CharField()
    count = serializers.IntegerField()


class AutogradingLanguageFailureSerializer(serializers.Serializer):
    language = serializers.CharField()
    executions = serializers.IntegerField()
    failures = serializers.IntegerField()
    failureRate = serializers.FloatField()


class AutogradingTopErrorSerializer(serializers.Serializer):
    # CharField, not ChoiceField, on purpose: no enum in the OpenAPI schema.
    category = serializers.CharField()
    count = serializers.IntegerField()
    sampleMessage = serializers.CharField(allow_blank=True)


class AutogradingStatsSerializer(serializers.Serializer):
    dateFrom = serializers.DateTimeField()
    dateTo = serializers.DateTimeField()
    totalRequests = serializers.IntegerField()
    cacheHits = serializers.IntegerField()
    actualExecutions = serializers.IntegerField()
    cacheHitRate = serializers.FloatField()
    failedExecutions = serializers.IntegerField()
    languageUsage = AutogradingLanguageUsageSerializer(many=True)
    failuresPerLanguage = AutogradingLanguageFailureSerializer(many=True)
    topErrors = AutogradingTopErrorSerializer(many=True)


class PendingAdminActionRequestSerializer(serializers.Serializer):
    user_email = serializers.EmailField()


class PendingAdminActionResponseSerializer(serializers.Serializer):
    status = serializers.CharField()
