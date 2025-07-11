from core.models import Comment
from core.serializers.comment import CommentSerializer, CommentBasicSerializer
from core.views.template import ListProtectedViewSet
from rest_framework.permissions import IsAuthenticated
from core.permissions.permissions import CommentPermissions
from rest_framework.response import Response
from rest_framework.decorators import action

from core.permissions.helpers import isStudentOfSub, isStaffOfSub

from core.permissions.helpers import returnNotAuthorized, returnForbidden

from rest_framework import serializers

class CommentViewSet(ListProtectedViewSet):
    """
    list:
    Return a list of all the comments.

    create:
    Create a new comment.

    retrieve:
    Return the given comment.

    update:
    Update a comment.

    partial_update:
    Update a comment.

    delete:
    Delete a comment.
    """
    queryset = Comment.objects.all()
    serializer_class = CommentSerializer
    permission_classes = (IsAuthenticated, CommentPermissions)

    def retrieve(self, request, pk=None):
        user = request.user
        comment = self.get_object()
        submission = comment.file.submission
        assignment = submission.assignment

        # We can assume that the retrieving user has privileges under
        # [isStudentOfSub, isStaffOfSub] since this is the definition of
        # the object permissions model (core.permissions.CommentPermissions)
        if isStudentOfSub(user,submission) and assignment.hideGradersFromStudents:
          serializer = CommentBasicSerializer(comment)
        else:
          serializer = CommentSerializer(comment)

        return Response(serializer.data)

    @action(detail=True, methods=['PATCH'])
    def feedback(self, request, pk=None):
        user = request.user

        # hack: avoid triggering PATCH permissions for Comment object
        comment = Comment.objects.get(id=pk)

        # only students of this submission's pareant comment should be able to leave
        # feedback on a comment
        if not isStudentOfSub(user, comment.file.submission):
            return returnForbidden()

        # manually validate feedback body
        feedback = int(request.data['feedback'])
        ALLOWED_FEEDBACK_VALUES = [-1, 0, 1]
        if feedback not in ALLOWED_FEEDBACK_VALUES:
            raise serializers.ValidationError("Feedback must be in " + str(ALLOWED_FEEDBACK_VALUES))
        else:
            comment.feedback = feedback
            comment.save()
            return Response(CommentBasicSerializer(comment).data)
