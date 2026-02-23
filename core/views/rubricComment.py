# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from core.models import RubricComment
from core.serializers.rubricComment import RubricCommentSerializer
from core.views.template import ListProtectedViewSet
from rest_framework.permissions import IsAuthenticated
from core.permissions.permissions import RubricCommentPermissions

from rest_framework.decorators import action
from rest_framework.response import Response

from core.permissions.helpers import isCourseStaff, isCourseAdmin
from core.permissions.helpers import returnForbidden

class RubricCommentViewSet(ListProtectedViewSet):
    """
    list:
    Return a list of all the rubric comments.

    create:
    Create a new rubric comment.

    retrieve:
    Return the given rubric comment.

    update:
    Update a rubric comment.

    partial_update:
    Update a rubric comment.

    delete:
    Delete a rubric comment.
    """
    queryset = RubricComment.objects.all()
    serializer_class = RubricCommentSerializer
    permission_classes = (IsAuthenticated, RubricCommentPermissions)

    @action(detail=True)
    def comments(self, request, pk=None):
        user = self.request.user
        rubricComment = self.get_object()
        course = rubricComment.category.assignment.course

        if not isCourseStaff(user, course):
            return returnForbidden()

        comments = list(map(lambda x : x['id'], rubricComment.comments.values('id')))

        toRet = {
            'id': rubricComment.id,
            'comments': comments
        }

        return Response(toRet)

    @action(detail=True)
    def feedbackScore(self, request, pk=None):
        user = self.request.user
        rubricComment = self.get_object()
        course = rubricComment.category.assignment.course

        if not isCourseAdmin(user, course):
            return returnForbidden()

        comments = list(map(lambda x : x['feedback'], rubricComment.comments.values('feedback')))

        toRet = {
            'id': rubricComment.id,
            'negative': len([x for x in comments if x == -1]) / len(comments) if len(comments) > 0 else 0,
            'positive': len([x for x in comments if x == 1]) / len(comments) if len(comments) > 0 else 0
        }

        return Response(toRet)
