# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from core.models import Section, Submission, Assignment

from core.serializers.section import SectionSerializer
from core.serializers.submission import AnonymousSubmissionSerializer, SubmissionSerializer

from core.views.template import ListProtectedViewSet
from rest_framework.permissions import IsAuthenticated
from core.permissions.permissions import SectionPermissions
from core.permissions.helpers import returnForbidden, canViewUnanonymizedSubmissions

from rest_framework.response import Response

from rest_framework.decorators import action
from drf_spectacular.utils import extend_schema, OpenApiParameter

class SectionViewSet(ListProtectedViewSet):
  """
  list:
  Return a list of all the sections.

  create:
  Create a new section.

  retrieve:
  Return the given section.

  update:
  Update a section.

  partial_update:
  Update a section.

  delete:
  Delete a section.
  """
  queryset = Section.objects.all()
  serializer_class = SectionSerializer
  permission_classes = (IsAuthenticated, SectionPermissions)

  @extend_schema(
      responses=SubmissionSerializer(many=True),
      parameters=[
          OpenApiParameter(name="assignment", required=True, type=int, location=OpenApiParameter.QUERY),
      ],
  )
  @action(detail=True, methods=["GET"])
  def submissions(self, request, pk=None):
    """
    Grab submissions corresponding to students in a section
    """
    user = self.request.user
    section = self.get_object()
    aid = self.request.query_params.get('assignment', None)
    course = section.course

    if not aid:
        return returnForbidden()

    try:
        assignment = Assignment.objects.get(id=int(aid))
    except Assignment.DoesNotExist:
        return returnForbidden()

    submissions = Submission.objects.filter(students__in=section.students.all(), assignment=assignment)

    if assignment.anonymousGrading and not canViewUnanonymizedSubmissions(user, course):
        serializer = AnonymousSubmissionSerializer(submissions, many=True, context={'request': request})
    else:
        serializer = SubmissionSerializer(submissions, many=True, context={'request': request})

    return Response(serializer.data)


