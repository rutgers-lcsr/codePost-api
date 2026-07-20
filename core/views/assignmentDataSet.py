# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""
Assignment Dataset API Views

Provides REST API endpoints for managing datasets associated with assignments.
Datasets are mounted into execution containers at specified paths (e.g., ~/shared/dataset_name).
"""

import logging
from typing import cast

from django.http import FileResponse, Http404
from drf_spectacular.utils import extend_schema, OpenApiParameter
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response

from core.models import Assignment, AssignmentDataSet, User
from core.permissions.capabilities import require_capability
from core.permissions.helpers import (
    isAuthenticated,
    returnForbidden,
    returnNotAuthorized,
)
from core.serializers.assignmentDataSet import (
    AssignmentDataSetSerializer,
    AssignmentDataSetCreateSerializer,
    AssignmentDataSetUpdateSerializer,
)

logger = logging.getLogger(__name__)


class AssignmentDataSetViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing assignment datasets
    
    Datasets are files (compressed or raw) that are mounted into the execution
    environment when students submit code or when code is executed via the API.
    
    Typical use case: Large training datasets for ML assignments
    """
    
    queryset = AssignmentDataSet.objects.all()
    serializer_class = AssignmentDataSetSerializer
    parser_classes = (MultiPartParser, FormParser, JSONParser)
    
    def get_serializer_class(self):
        """Use different serializers for different actions"""
        if self.action == 'create':
            return AssignmentDataSetCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return AssignmentDataSetUpdateSerializer
        return AssignmentDataSetSerializer
    
    def get_queryset(self):
        """Filter datasets based on user permissions.

        Staff (course admins/graders/super graders) see every dataset in their courses.
        Students see shared (non-hidden) datasets, plus — for a per-student variant pool
        (is_student_variant=True) — only the one variant already assigned to them via
        StudentDataSetAssignment. This governs list() directly and, via get_object()'s
        queryset filtering, retrieve()/download() too: a dataset the student can't see
        404s rather than confirming it exists.
        """
        user = cast(User, self.request.user)

        if not isAuthenticated(user):
            return AssignmentDataSet.objects.none()

        # Superusers see all datasets
        if user.is_superuser:
            return AssignmentDataSet.objects.all()

        from django.db.models import Q

        staff_query = Q(assignment__course__courseAdmins=user) | \
                      Q(assignment__course__graders=user) | \
                      Q(assignment__course__superGraders=user)
        staff_qs = AssignmentDataSet.objects.filter(staff_query)

        student_qs = AssignmentDataSet.objects.filter(
            assignment__course__students=user, hidden=False,
        ).exclude(Q(is_student_variant=True) & ~Q(student_assignments__student=user))

        return (staff_qs | student_qs).distinct()
    
    def create(self, request, *args, **kwargs):
        """Create a new dataset"""
        if not isAuthenticated(request.user):
            return returnNotAuthorized()
        
        # Check if user can admin the assignment's course
        assignment_id = request.data.get('assignment')
        if not assignment_id:
            return Response(
                {"error": "assignment field is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            assignment = Assignment.objects.get(id=assignment_id)
        except Assignment.DoesNotExist:
            return Response(
                {"error": "Assignment not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        require_capability(request.user, 'manage_datasets', assignment)
        
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            dataset = serializer.save()
            
            logger.info(
                f"[AssignmentDataSet] Created dataset '{dataset.name}' "
                f"for assignment {assignment.id} by user {cast(User, request.user).username}"
            )
            
            # Return full representation
            output_serializer = AssignmentDataSetSerializer(
                dataset,
                context={'request': request}
            )
            return Response(
                output_serializer.data,
                status=status.HTTP_201_CREATED
            )
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def retrieve(self, request, *args, **kwargs):
        """Get a single dataset"""
        if not isAuthenticated(request.user):
            return returnNotAuthorized()
        
        dataset = self.get_object()
        
        # Check permissions
        if not self._can_access_dataset(request.user, dataset):
            return returnForbidden()
        
        serializer = self.get_serializer(dataset)
        return Response(serializer.data)
    
    def update(self, request, *args, **kwargs):
        """Update a dataset (metadata only, not file)"""
        if not isAuthenticated(request.user):
            return returnNotAuthorized()
        
        dataset = self.get_object()
        
        require_capability(request.user, 'manage_datasets', dataset.assignment)
        
        partial = kwargs.pop('partial', False)
        serializer = self.get_serializer(dataset, data=request.data, partial=partial)
        
        if serializer.is_valid():
            dataset = serializer.save()
            
            logger.info(
                f"[AssignmentDataSet] Updated dataset {dataset.id} "
                f"by user {cast(User, request.user).username}"
            )
            
            # Return full representation
            output_serializer = AssignmentDataSetSerializer(
                dataset,
                context={'request': request}
            )
            return Response(output_serializer.data)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def destroy(self, request, *args, **kwargs):
        """Delete a dataset"""
        if not isAuthenticated(request.user):
            return returnNotAuthorized()
        
        dataset = self.get_object()
        
        require_capability(request.user, 'manage_datasets', dataset.assignment)
        
        dataset_id = dataset.id
        dataset_name = dataset.name
        
        # Delete the file from storage
        if dataset.file:
            try:
                dataset.file.delete(save=False)
            except Exception as e:
                logger.warning(f"Failed to delete dataset file: {e}")
        
        dataset.delete()
        
        logger.info(
            f"[AssignmentDataSet] Deleted dataset {dataset_id} ('{dataset_name}') "
            f"by user {cast(User, request.user).username}"
        )
        
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        request={'application/json': {
            'type': 'object',
            'properties': {
                'rowsPerChunk': {'type': 'integer', 'minimum': 1},
                'hasHeader': {'type': 'boolean'},
            },
            'required': ['rowsPerChunk'],
        }},
        responses=AssignmentDataSetSerializer(many=True),
    )
    @action(detail=True, methods=['post'])
    def splitIntoVariants(self, request, pk=None):
        """
        Split this dataset's file into disjoint row-chunks, one per generated variant,
        forming a per-student pool (see core.services.dataset_split). The chunk count is
        driven by rowsPerChunk, not current enrollment, so the pool stays stable as
        students enroll or drop.

        POST /assignmentDataSets/{id}/splitIntoVariants/
        """
        if not isAuthenticated(request.user):
            return returnNotAuthorized()

        master = self.get_object()
        require_capability(request.user, 'manage_datasets', master.assignment)

        rows_per_chunk = request.data.get('rowsPerChunk')
        try:
            rows_per_chunk = int(rows_per_chunk)
        except (TypeError, ValueError):
            return Response({"error": "rowsPerChunk must be an integer."},
                            status=status.HTTP_400_BAD_REQUEST)
        has_header = bool(request.data.get('hasHeader', True))

        from core.services.dataset_split import DatasetSplitError, split_master_dataset
        try:
            chunks = split_master_dataset(master, rows_per_chunk, has_header)
        except DatasetSplitError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        logger.info(
            f"[AssignmentDataSet] Split dataset {master.id} ('{master.name}') into "
            f"{len(chunks)} variants by user {cast(User, request.user).username}"
        )
        serializer = AssignmentDataSetSerializer(chunks, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'])
    def download(self, request, pk=None):
        """
        Download the dataset file
        
        GET /assignments/datasets/{id}/download/
        """
        if not isAuthenticated(request.user):
            return returnNotAuthorized()
        
        dataset = self.get_object()
        
        # Check permissions
        if not self._can_access_dataset(request.user, dataset):
            return returnForbidden()
        
        if not dataset.file:
            raise Http404("Dataset file not found")
        
        # Return file as response
        try:
            response = FileResponse(
                dataset.file.open('rb'),
                content_type='application/octet-stream'
            )
            
            # Set download filename
            filename = dataset.file.name.split('/')[-1]
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            
            logger.info(
                f"[AssignmentDataSet] User {request.user.username} "
                f"downloaded dataset {dataset.id} ('{dataset.name}')"
            )
            
            return response
            
        except Exception as e:
            logger.error(f"Failed to serve dataset file: {e}")
            return Response(
                {"error": "Failed to retrieve dataset file"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @extend_schema(
        parameters=[
            OpenApiParameter(name='assignment_id', required=True, type=int,
                             location=OpenApiParameter.QUERY,
                             description='The assignment whose datasets to list.'),
        ],
        responses=AssignmentDataSetSerializer(many=True),
    )
    @action(detail=False, methods=['get'])
    def by_assignment(self, request):
        """
        List datasets for a specific assignment
        
        GET /assignments/datasets/by_assignment/?assignment_id=123
        """
        if not isAuthenticated(request.user):
            return returnNotAuthorized()
        
        assignment_id = request.query_params.get('assignment_id')
        if not assignment_id:
            return Response(
                {"error": "assignment_id query parameter is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            assignment = Assignment.objects.get(id=assignment_id)
        except Assignment.DoesNotExist:
            return Response(
                {"error": "Assignment not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Check if user has access to the course
        if not self._can_access_course(request.user, assignment.course):
            return returnForbidden()

        user = cast(User, request.user)
        if self._is_course_staff(user, assignment.course):
            # Staff see everything (including inactive ones) for management.
            datasets = AssignmentDataSet.objects.filter(assignment=assignment).order_by('name')
        else:
            # Assign the student's variant now if this is their first time asking, so
            # "first access" actually shows them one instead of nothing.
            from django.db.models import Q
            from core.services.dataset_assignment import get_or_assign
            get_or_assign(assignment, user)
            datasets = AssignmentDataSet.objects.filter(
                assignment=assignment, hidden=False,
            ).exclude(Q(is_student_variant=True) & ~Q(student_assignments__student=user)).order_by('name')

        serializer = self.get_serializer(datasets, many=True)
        return Response(serializer.data)
    
    def _can_access_dataset(self, user, dataset):
        """Check if user can access a dataset"""
        course = dataset.assignment.course
        return self._can_access_course(user, course)

    def _is_course_staff(self, user, course):
        """Course admin, grader, or super grader (or superuser) — sees every dataset."""
        return (
            user.is_superuser or
            course.courseAdmins.filter(id=user.id).exists() or
            course.graders.filter(id=user.id).exists() or
            course.superGraders.filter(id=user.id).exists()
        )

    def _can_access_course(self, user, course):
        """Check if user has access to a course"""
        if user.is_superuser:
            return True
        
        return (
            course.courseAdmins.filter(id=user.id).exists() or
            course.graders.filter(id=user.id).exists() or
            course.superGraders.filter(id=user.id).exists() or
            course.students.filter(id=user.id).exists()
        )
