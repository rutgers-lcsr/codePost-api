# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from rest_framework import serializers
from core.models import QuizImage


class QuizImageSerializer(serializers.ModelSerializer):
  """Read view of an uploaded description image. ``url`` is the public, token-based
  endpoint that renders inline in Markdown."""
  url = serializers.SerializerMethodField()

  class Meta:
    model = QuizImage
    fields = ('id', 'course', 'token', 'url', 'originalName', 'contentType', 'created')
    read_only_fields = ('token', 'url', 'originalName', 'contentType', 'created')

  def get_url(self, obj) -> str:
    path = f'/quizImages/raw/{obj.token}/'
    request = self.context.get('request')
    return request.build_absolute_uri(path) if request is not None else path
