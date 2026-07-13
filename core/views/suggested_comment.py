# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from drf_spectacular.utils import extend_schema

from core.models import SuggestedComment, Comment
from core.serializers.suggested_comment import SuggestedCommentSerializer
from core.serializers.comment import CommentSerializer
from core.views.template import ListProtectedViewSet
from rest_framework.permissions import IsAuthenticated
from core.permissions.permissions import SuggestedCommentPermissions
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework import status

from core.permissions.helpers import isStaffOfSub, returnForbidden

from logging import getLogger
logger = getLogger(__name__)


class SuggestedCommentViewSet(ListProtectedViewSet):
    """
    AI-suggested comments for graders. Not visible to students.

    retrieve:
    Return a suggested comment.

    delete:
    Delete a suggested comment.
    """
    queryset = SuggestedComment.objects.select_related(
        'submission', 'submission__assignment', 'submission__assignment__course',
        'file', 'rubricComment', 'acceptedBy', 'acceptedComment',
    ).all()
    serializer_class = SuggestedCommentSerializer
    permission_classes = (IsAuthenticated, SuggestedCommentPermissions)

    @extend_schema(
        responses=CommentSerializer,
        description="Accept this suggestion, creating a real Comment and marking the suggestion as accepted.",
    )
    @action(detail=True, methods=['POST'])
    def accept(self, request, pk=None):
        """Accept an AI suggestion, converting it into a real Comment."""
        suggestion = self.get_object()
        user = request.user

        if not isStaffOfSub(user, suggestion.submission):
            return returnForbidden()

        if suggestion.status != 'pending':
            return Response(
                {'error': f'Suggestion is already {suggestion.status}.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Resolve pointDelta: use rubricComment's pointDelta when suggestion has none
        point_delta = suggestion.pointDelta
        if point_delta is None and suggestion.rubricComment is not None:
            point_delta = suggestion.rubricComment.pointDelta

        # Create the real comment from suggestion data
        comment = Comment.objects.create(
            text=suggestion.text,
            pointDelta=point_delta,
            rubricComment=suggestion.rubricComment,
            author=user,
            file=suggestion.file,
            startLine=suggestion.startLine,
            endLine=suggestion.endLine,
            startChar=suggestion.startChar,
            endChar=suggestion.endChar,
        )

        # Mark suggestion as accepted
        suggestion.status = 'accepted'
        suggestion.acceptedBy = user
        suggestion.acceptedComment = comment
        suggestion.save()

        logger.info(f"Suggestion {suggestion.id} accepted by {user.email}, created comment {comment.id}")
        return Response(CommentSerializer(comment).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        responses=SuggestedCommentSerializer,
        description="Reject this suggestion.",
    )
    @action(detail=True, methods=['POST'])
    def reject(self, request, pk=None):
        """Reject an AI suggestion."""
        suggestion = self.get_object()
        user = request.user

        if not isStaffOfSub(user, suggestion.submission):
            return returnForbidden()

        if suggestion.status != 'pending':
            return Response(
                {'error': f'Suggestion is already {suggestion.status}.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        suggestion.status = 'rejected'
        suggestion.save()

        logger.info(f"Suggestion {suggestion.id} rejected by {user.email}")
        return Response(SuggestedCommentSerializer(suggestion).data)
