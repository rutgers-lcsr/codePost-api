# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from django.core.exceptions import ValidationError
from django.http import FileResponse, HttpResponseNotFound
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.models import Course, QuizImage
from core.serializers.quizImage import QuizImageSerializer
from core.views.template import ListProtectedViewSet
from core.permissions.permissions import QuizImagePermissions
from core.permissions.helpers import isCourseStaff, returnForbidden

# Raster formats only — SVG is excluded to avoid script-bearing images.
ALLOWED_IMAGE_TYPES = {'image/png', 'image/jpeg', 'image/gif', 'image/webp'}
MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB


class QuizImageViewSet(ListProtectedViewSet):
  """Instructor-uploaded images for quiz/question/bank Markdown descriptions."""
  queryset = QuizImage.objects.select_related('course').all()
  serializer_class = QuizImageSerializer
  permission_classes = (IsAuthenticated, QuizImagePermissions)
  parser_classes = (MultiPartParser, FormParser)

  @extend_schema(responses=QuizImageSerializer)
  def create(self, request, *args, **kwargs):
    course = get_object_or_404(Course, id=request.data.get('course'))
    if not (request.user.is_superuser or isCourseStaff(request.user, course)):
      return returnForbidden()

    upload = request.FILES.get('image')
    if upload is None:
      return Response({'error': 'An image file is required (multipart "image").'},
                      status=status.HTTP_400_BAD_REQUEST)
    if upload.size > MAX_IMAGE_BYTES:
      return Response({'error': 'Image too large (max 5 MB).'}, status=status.HTTP_400_BAD_REQUEST)
    content_type = (getattr(upload, 'content_type', '') or '').lower()
    if content_type not in ALLOWED_IMAGE_TYPES:
      return Response({'error': 'Unsupported image type. Use PNG, JPEG, GIF, or WebP.'},
                      status=status.HTTP_400_BAD_REQUEST)

    image = QuizImage.objects.create(
        course=course, image=upload, originalName=(upload.name or '')[:255],
        contentType=content_type, uploadedBy=request.user,
    )
    return Response(QuizImageSerializer(image, context={'request': request}).data,
                    status=status.HTTP_201_CREATED)


def serve_quiz_image(request, token):
  """Public, unauthenticated image serving by unguessable token. Plain Django view so
  it bypasses DRF auth — required because <img> requests carry no Authorization header.
  The token (uuid4) is the access control; only validated image types are ever stored."""
  try:
    image = QuizImage.objects.get(token=token)
  except (QuizImage.DoesNotExist, ValidationError, ValueError):
    return HttpResponseNotFound()
  try:
    fh = image.image.open('rb')
  except (FileNotFoundError, ValueError):
    return HttpResponseNotFound()
  response = FileResponse(fh, content_type=image.contentType or 'application/octet-stream')
  response['Cache-Control'] = 'public, max-age=31536000, immutable'
  response['X-Content-Type-Options'] = 'nosniff'
  return response
