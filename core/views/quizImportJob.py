# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.models import Course, QuestionBank, QuizImportJob
from core.serializers.quizImportJob import QuizImportJobSerializer
from core.views.template import ListProtectedViewSet
from core.permissions.permissions import QuizImportPermissions
from core.permissions.helpers import isCourseStaff, returnForbidden


class QuizImportJobViewSet(ListProtectedViewSet):
  """Import quizzes/question banks from a QTI / Common Cartridge export
  (e.g. exported from Canvas or another LMS).

  create:
  Upload a QTI / Common Cartridge export (multipart ``file``) for a ``course``. Optionally
  target an existing bank (``targetBankId``) or name a new one (``bankName``). Parsing runs
  asynchronously; poll the returned job via ``retrieve``.

  retrieve:
  Return the import job's current status, counts, and parse summary.
  """
  queryset = QuizImportJob.objects.select_related('course', 'targetBank', 'createdBy').all()
  serializer_class = QuizImportJobSerializer
  permission_classes = (IsAuthenticated, QuizImportPermissions)
  parser_classes = (MultiPartParser, FormParser, JSONParser)

  @extend_schema(responses=QuizImportJobSerializer)
  def create(self, request, *args, **kwargs):
    course = get_object_or_404(Course, id=request.data.get('course'))
    if not (request.user.is_superuser or isCourseStaff(request.user, course)):
      return returnForbidden()

    upload = request.FILES.get('file')
    if upload is None:
      return Response({'error': 'A QTI / Common Cartridge export file is required (multipart "file").'},
                      status=status.HTTP_400_BAD_REQUEST)

    target_bank = None
    bank_id = request.data.get('targetBankId') or request.data.get('targetBank')
    if bank_id:
      target_bank = QuestionBank.objects.filter(id=bank_id, course=course).first()
    elif request.data.get('bankName'):
      target_bank, _ = QuestionBank.objects.get_or_create(
          course=course, name=request.data['bankName'],
          defaults={'source': 'imported', 'createdBy': request.user},
      )

    job = QuizImportJob.objects.create(
        course=course, createdBy=request.user, file=upload,
        targetBank=target_bank, status='pending',
    )

    import_quizzes = str(request.data.get('importQuizzes', '')).lower() in ('1', 'true', 'yes', 'on')

    from core.tasks import import_quiz_qti
    task = import_quiz_qti.delay(job.id, import_quizzes=import_quizzes)
    # Use a queryset update (not job.save) to set taskId without BaseModel.save
    # recomputing update_fields from a now-stale instance — under eager Celery the
    # task may have already advanced status/counts on the DB row.
    QuizImportJob.objects.filter(pk=job.pk).update(taskId=task.id)

    job.refresh_from_db()
    return Response(QuizImportJobSerializer(job).data, status=status.HTTP_202_ACCEPTED)
