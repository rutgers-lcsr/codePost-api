# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial Licensed, included with this software.
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.models import ChatConversation, Submission
from core.serializers.chat import (
    ChatConversationCreateSerializer,
    ChatConversationDetailSerializer,
    ChatConversationListSerializer,
)
from core.views.template import ListProtectedViewSet
from core.permissions.helpers import isStaffOfSub, returnForbidden, returnNotFound

from logging import getLogger
logger = getLogger(__name__)


@extend_schema_view(
    list=extend_schema(
        description="List chat conversations for a submission.",
        parameters=[OpenApiParameter(name='submission', type=int, required=True)],
    ),
    create=extend_schema(description="Create a new chat conversation."),
    retrieve=extend_schema(description="Retrieve a conversation with all messages."),
    partial_update=extend_schema(description="Update a conversation (e.g., rename)."),
    destroy=extend_schema(description="Delete a conversation."),
)
class ChatConversationViewSet(ListProtectedViewSet):
    """
    CRUD endpoints for chat conversations in the grading assistant.

    list:
    List conversations for a submission (query param `?submission=ID`).

    create:
    Start a new conversation for a submission.

    retrieve:
    Get a conversation with its full message history.

    partial_update:
    Update a conversation title.

    destroy:
    Delete a conversation and all its messages.
    """
    serializer_class = ChatConversationListSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return ChatConversation.objects.filter(user=self.request.user)

    def get_serializer_class(self):
        if self.action == 'create':
            return ChatConversationCreateSerializer
        elif self.action == 'retrieve':
            return ChatConversationDetailSerializer
        return ChatConversationListSerializer

    def list(self, request):
        if not request.user.is_authenticated:
            return returnForbidden()

        submission_id = request.query_params.get('submission')
        if not submission_id:
            return Response(
                {"detail": "Query parameter 'submission' is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Verify permission on the submission
        try:
            submission = Submission.objects.select_related('assignment__course').get(pk=submission_id)
        except Submission.DoesNotExist:
            return returnNotFound()

        if not isStaffOfSub(request.user, submission):
            return returnForbidden()

        conversations = self.get_queryset().filter(submission_id=submission_id)
        serializer = self.get_serializer(conversations, many=True)
        return Response(serializer.data)

    def create(self, request):
        serializer = ChatConversationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        submission = serializer.validated_data['submission']

        # Verify permission
        try:
            sub = Submission.objects.select_related('assignment__course').get(pk=submission.id)
        except Submission.DoesNotExist:
            return returnNotFound()

        if not isStaffOfSub(request.user, sub):
            return returnForbidden()

        conversation = serializer.save(
            user=request.user,
            assignment=sub.assignment,
        )
        return Response(
            ChatConversationListSerializer(conversation).data,
            status=status.HTTP_201_CREATED,
        )

    def retrieve(self, request, pk=None):
        try:
            conversation = self.get_queryset().prefetch_related('messages').get(pk=pk)
        except ChatConversation.DoesNotExist:
            return returnNotFound()

        # Verify permission on the submission
        try:
            sub = Submission.objects.select_related('assignment__course').get(pk=conversation.submission_id)
        except Submission.DoesNotExist:
            return returnNotFound()

        if not isStaffOfSub(request.user, sub):
            return returnForbidden()

        serializer = ChatConversationDetailSerializer(conversation)
        return Response(serializer.data)

    def partial_update(self, request, pk=None):
        try:
            conversation = self.get_queryset().get(pk=pk)
        except ChatConversation.DoesNotExist:
            return returnNotFound()

        # Only allow updating title
        title = request.data.get('title')
        if title is not None:
            conversation.title = title[:200]
            conversation.save()

        return Response(ChatConversationListSerializer(conversation).data)

    def destroy(self, request, pk=None):
        try:
            conversation = self.get_queryset().get(pk=pk)
        except ChatConversation.DoesNotExist:
            return returnNotFound()

        conversation.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
