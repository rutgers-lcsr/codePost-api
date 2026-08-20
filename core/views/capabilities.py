# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
import re

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes

from core.permissions.capabilities import (
    compute_platform_capabilities,
    compute_course_capabilities,
    compute_assignment_capabilities,
    compute_submission_capabilities,
    Capability,
    CAPABILITY_DESCRIPTIONS,
)
from core.permissions.role_cache import RoleCache
from core.permissions.course_scope import get_course_scope_id
from core.serializers.actionResponses import (
    CapabilitiesResponseSerializer,
    BatchCapabilitiesRequestSerializer,
    BatchCapabilitiesResponseSerializer,
)


class PlatformCapabilitiesView(APIView):
    """Return the requesting user's platform-level capabilities."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses={
            200: CapabilitiesResponseSerializer,
        },
        parameters=[
            OpenApiParameter(
                name='descriptions',
                type=OpenApiTypes.BOOL,
                location=OpenApiParameter.QUERY,
                required=False,
                description='Include human-readable descriptions for each capability.',
            ),
        ],
        tags=['capabilities'],
    )
    def get(self, request):
        caps = compute_platform_capabilities(request.user)

        include_descriptions = request.query_params.get('descriptions', '').lower() in ('true', '1')
        if include_descriptions:
            descriptions = {
                cap: CAPABILITY_DESCRIPTIONS.get(Capability(cap), '')
                for cap in caps
            }
            return Response({'capabilities': caps, 'descriptions': descriptions})

        return Response({'capabilitiesMap': caps})


# ---------------------------------------------------------------------------
# Key format for batch requests
# ---------------------------------------------------------------------------
_KEY_PATTERN = re.compile(r'^(course|assignment|submission):(\d+)$')


class BatchCapabilitiesView(APIView):
    """Return capabilities for multiple resources in a single request.

    Accepts up to 20 keys like ``"course:1"``, ``"assignment:5"``,
    ``"submission:42"``, or ``"platform"``.  Returns a map of key →
    capability dict.  Invalid or inaccessible keys are silently skipped.

    A shared ``RoleCache`` is used across all computations so that
    role-check DB queries are deduplicated.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=BatchCapabilitiesRequestSerializer,
        responses={200: BatchCapabilitiesResponseSerializer},
        tags=['capabilities'],
    )
    def post(self, request):
        serializer = BatchCapabilitiesRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        keys = serializer.validated_data['keys']

        # Local imports to avoid circular imports at module level
        from core.models import Course, Assignment, Submission

        user = request.user
        rc = RoleCache(user)
        is_scoped = get_course_scope_id(request) is not None
        results: dict[str, dict] = {}

        for key in keys:
            if key == 'platform':
                results[key] = compute_platform_capabilities(user)
                continue

            match = _KEY_PATTERN.match(key)
            if not match:
                continue  # skip invalid keys

            scope, obj_id = match.group(1), int(match.group(2))
            try:
                if scope == 'course':
                    obj = Course.objects.get(pk=obj_id)
                    caps = compute_course_capabilities(user, obj, is_course_scoped=is_scoped, _rc=rc)
                    if not caps.get(Capability.VIEW_COURSE):
                        continue
                    results[key] = caps
                elif scope == 'assignment':
                    obj = Assignment.objects.select_related('course').get(pk=obj_id)
                    caps = compute_assignment_capabilities(user, obj, _rc=rc)
                    if not caps.get(Capability.VIEW_ASSIGNMENT):
                        continue
                    results[key] = caps
                elif scope == 'submission':
                    obj = Submission.objects.select_related('assignment__course').get(pk=obj_id)
                    caps = compute_submission_capabilities(user, obj, _rc=rc)
                    if not caps.get(Capability.VIEW_SUBMISSION):
                        continue
                    results[key] = caps
            except (Course.DoesNotExist, Assignment.DoesNotExist, Submission.DoesNotExist):
                continue  # skip non-existent resources

        return Response({'results': results})
