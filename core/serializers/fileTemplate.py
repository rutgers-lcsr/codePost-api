# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from core.serializers.template import ModelSerializerWithPOSTCheck
from core.models import FileTemplate


class FileTemplateSerializer(ModelSerializerWithPOSTCheck):

  class Meta:
    model = FileTemplate
    fields = ('name', 'data', 'extension', 'id', 'path', 'assignment', 'required', 'description')
    extra_kwargs = {
        "data": {"trim_whitespace": False},
    }
