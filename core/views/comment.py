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
from logging import getLogger
logger = getLogger(__name__)


def _format_points_str(point_delta) -> str:
    """Format a point delta into a human-readable string for AI context."""
    try:
        point_delta = float(point_delta)
    except (ValueError, TypeError):
        point_delta = 0
    
    if point_delta > 0:
        return f"Deduction: {point_delta} points"
    elif point_delta < 0:
        return f"Bonus: {abs(point_delta)} points"
    else:
        return "Points: 0"

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

    @action(detail=False, methods=['POST'])
    def generate(self, request):
        """
        Generate an AI-powered comment suggestion. 
        
        Note: The system prompt determines what gets put into the comments context. This way the instructor can define what we add. If they want all the files they can add all the files. if they just want the current file we can. This way we can make the objective turth of the system prompt be from the instructor. The frontend should let the instructor know what varibles to use to enable what we put into the system prompt. 

        Request body:
        - file_id: int (required) - ID of the SubmissionFile
        - start_line: int (required) - Start line of selection (0-indexed)
        - end_line: int (required) - End line of selection (0-indexed)
        - rubric_comment_id: int (optional) - ID of linked RubricComment
        - existing_text: str (optional) - Grader's draft text to improve
        """
        from asgiref.sync import async_to_sync
        from rest_framework import status
        from core.models import SubmissionFile, RubricComment
        from core.services.ai_service import AIService, build_context_from_file, GenerationContext
        from core.permissions.helpers import isAuthenticated

        user = request.user
        if not isAuthenticated(user):
            return returnNotAuthorized()

        # Parse request data
        file_id = request.data.get('file_id')
        start_line = request.data.get('start_line')
        end_line = request.data.get('end_line')
        rubric_comment_id = request.data.get('rubric_comment_id')
        existing_text = request.data.get('existing_text', '')
        points_override = request.data.get('points')

        # Validate required fields
        if not file_id or start_line is None or end_line is None:
            return Response(
                {'error': 'file_id, start_line, and end_line are required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            file = SubmissionFile.objects.get(id=file_id)
        except SubmissionFile.DoesNotExist:
            return Response(
                {'error': 'File not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Check permissions - only staff can generate comments
        if not isStaffOfSub(user, file.submission):
            return returnForbidden()

        # Get course and check if AI is configured
        course = file.submission.assignment.course
        assignment = file.submission.assignment

        if not course.ai_provider or not course.ai_api_key or course.ai_disabled:
            return Response(
                {'error': 'AI is not available. Please ask your instructor if you think this is a problem.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Build context
        context = build_context_from_file(
            file=file,
            start_line=start_line,
            end_line=end_line,
        )
        
        # Add supplementary context
        request_context = {
            'grader_draft': existing_text,
        }
        
        # Add rubric context if provided
        if rubric_comment_id:
            try:
                rubric_comment = RubricComment.objects.get(id=rubric_comment_id)
                # Use points override if provided, otherwise default to rubric comment pointDelta
                point_delta = points_override if points_override is not None else rubric_comment.pointDelta
                points_str = _format_points_str(point_delta)
                
                request_context['rubric_context'] = (
                    f"Rubric Item: {rubric_comment.text}\n"
                    f"Category: {rubric_comment.category.name}\n"
                    f"Description: {rubric_comment.explanation}\n"
                    f"{points_str}"
                )
            except RubricComment.DoesNotExist:
                logger.warning(f"Rubric comment {rubric_comment_id} not found")
        elif points_override is not None:
            # Handle manual points without rubric
            points_str = _format_points_str(points_override)
            
            request_context['rubric_context'] = (
                f"Manual Points Adjustment\n"
                f"{points_str}"
            )

        # Update context helper
        context.grader_draft = request_context.get('grader_draft', '')
        context.rubric_context = request_context.get('rubric_context', '')
        
        # Generate comment
        service = AIService(course, assignment)
        result = async_to_sync(service.generate_comment)(context)

        if result.success:
            return Response({'text': result.text})
        else:
            return Response(
                {'error': result.error or 'Generation failed'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )