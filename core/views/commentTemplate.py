from rest_framework import viewsets, permissions, filters
from django_filters.rest_framework import DjangoFilterBackend
from core.models import CommentTemplate
from core.serializers.commentTemplate import CommentTemplateSerializer
from django.db.models import Q

class CommentTemplateViewSet(viewsets.ModelViewSet):
    serializer_class = CommentTemplateSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['assignment', 'filePath']
    search_fields = ['text', 'filePath']

    def get_queryset(self):
        # During schema generation, return empty queryset
        if getattr(self, 'swagger_fake_view', False):
            return CommentTemplate.objects.none()
            
        user = self.request.user
        # Return templates that are either owned by the user or global
        return CommentTemplate.objects.filter(Q(owner=user) | Q(isGlobal=True))

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)
