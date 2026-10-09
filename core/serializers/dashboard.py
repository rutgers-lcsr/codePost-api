# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from drf_spectacular.utils import extend_schema_field
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


class AutogradingAssignmentFailureSerializer(serializers.Serializer):
    courseId = serializers.IntegerField(allow_null=True)
    courseName = serializers.CharField(allow_null=True)
    coursePeriod = serializers.CharField(allow_null=True)
    assignmentId = serializers.IntegerField()
    assignmentName = serializers.CharField()
    failures = serializers.IntegerField()
    topCategory = serializers.CharField()


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
    failuresByAssignment = AutogradingAssignmentFailureSerializer(many=True)


class AutogradingFailureSerializer(serializers.Serializer):
    """One failed autograder execution with everything needed to isolate it.
    Plain Serializer (not ModelSerializer) so no enum lands in the schema."""
    id = serializers.IntegerField()
    created = serializers.DateTimeField()
    trigger = serializers.CharField()
    language = serializers.CharField(allow_blank=True)
    category = serializers.CharField(source='error_category', allow_blank=True)
    errorMessage = serializers.CharField(source='error_message', allow_blank=True)
    errorDetail = serializers.CharField(source='error_detail', allow_blank=True)
    courseId = serializers.IntegerField(source='course_id', allow_null=True)
    courseName = serializers.SerializerMethodField()
    coursePeriod = serializers.SerializerMethodField()
    assignmentId = serializers.IntegerField(source='assignment_id', allow_null=True)
    assignmentName = serializers.SerializerMethodField()
    submissionId = serializers.IntegerField(source='submission_id', allow_null=True)
    fileId = serializers.IntegerField(source='file_id', allow_null=True)
    fileName = serializers.CharField(source='file_name', allow_blank=True)
    triggeredBy = serializers.SerializerMethodField()
    imageName = serializers.CharField(source='image_name', allow_blank=True)
    taskId = serializers.CharField(source='task_id', allow_blank=True)
    executionTime = serializers.FloatField(source='execution_time', allow_null=True)

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_courseName(self, obj):
        return obj.course.name if obj.course else None

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_coursePeriod(self, obj):
        return obj.course.period if obj.course else None

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_assignmentName(self, obj):
        return obj.assignment.name if obj.assignment else None

    @extend_schema_field(serializers.EmailField(allow_null=True))
    def get_triggeredBy(self, obj):
        return obj.triggered_by.email if obj.triggered_by else None


class AutogradingFailureListSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    pageSize = serializers.IntegerField()
    results = AutogradingFailureSerializer(many=True)


class PendingAdminActionRequestSerializer(serializers.Serializer):
    user_email = serializers.EmailField()


class PendingAdminActionResponseSerializer(serializers.Serializer):
    status = serializers.CharField()
