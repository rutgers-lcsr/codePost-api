# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""Staff-only view of per-student dataset variant assignments.

Rows are created automatically on first access (see core.services.dataset_assignment) —
this API is read-only plus a single override action, never create/delete.
"""
from typing import cast

from django.db.models import Q
from drf_spectacular.utils import extend_schema, OpenApiParameter
from rest_framework import status, viewsets
from rest_framework.response import Response

from core.models import Assignment, StudentDataSetAssignment, User
from core.permissions.capabilities import require_capability
from core.permissions.helpers import isAuthenticated, returnNotAuthorized
from core.serializers.studentDataSetAssignment import StudentDataSetAssignmentSerializer


class StudentDataSetAssignmentViewSet(viewsets.ModelViewSet):
    """list: mappings for one assignment (?assignment=<id>, required).
    partial_update: override a student's assigned variant."""

    http_method_names = ['get', 'patch', 'head', 'options']
    queryset = StudentDataSetAssignment.objects.select_related('student', 'dataset', 'assignedBy').all()
    serializer_class = StudentDataSetAssignmentSerializer

    def get_queryset(self):
        user = cast(User, self.request.user)
        if not isAuthenticated(user):
            return StudentDataSetAssignment.objects.none()
        if user.is_superuser:
            return super().get_queryset()
        return super().get_queryset().filter(
            Q(assignment__course__courseAdmins=user) |
            Q(assignment__course__graders=user) |
            Q(assignment__course__superGraders=user)
        ).distinct()

    @extend_schema(
        parameters=[
            OpenApiParameter(name='assignment', required=True, type=int,
                             location=OpenApiParameter.QUERY,
                             description='The assignment whose dataset-variant mappings to list.'),
        ],
        responses=StudentDataSetAssignmentSerializer(many=True),
    )
    def list(self, request, *args, **kwargs):
        if not isAuthenticated(request.user):
            return returnNotAuthorized()
        assignment_id = request.query_params.get('assignment')
        if not assignment_id:
            return Response({"error": "assignment query parameter is required"},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            assignment = Assignment.objects.get(id=assignment_id)
        except Assignment.DoesNotExist:
            return Response({"error": "Assignment not found"}, status=status.HTTP_404_NOT_FOUND)
        require_capability(request.user, 'manage_datasets', assignment)
        queryset = self.get_queryset().filter(assignment=assignment).order_by('student__email')
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def partial_update(self, request, *args, **kwargs):
        if not isAuthenticated(request.user):
            return returnNotAuthorized()
        instance = self.get_object()
        require_capability(request.user, 'manage_datasets', instance.assignment)
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save(assignedBy=cast(User, request.user))
        return Response(serializer.data)
