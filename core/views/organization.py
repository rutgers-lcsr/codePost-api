from core.models import Organization
from core.serializers.organization import OrganizationSerializer
from core.views.template import SuperUserListProtectedViewSet
from rest_framework.permissions import IsAuthenticated
from core.permissions.permissions import OrganizationPermissions
from rest_framework.decorators import permission_classes as api_permission_classes, action
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth.models import User
from core.serializers.user import UserSerializer
from core.permissions.helpers import returnForbidden, returnNotFound



class OrganizationViewSet(SuperUserListProtectedViewSet):
  """
  list:
  Return a list of all the organizations.

  create:
  Create a new organization.

  retrieve:
  Return the given organization.

  update:
  Update an organization.

  partial_update:
  Update an organization.

  delete:
  Delete an organization
  """
  queryset = Organization.objects.all()
  serializer_class = OrganizationSerializer
  permission_classes = (IsAuthenticated, OrganizationPermissions)

  def get_permissions(self):
    if self.action in ['verify_user', 'promote_staff', 'demote_staff', 'remove_user', 'reset_user_password', 'analytics']:
      return [IsAuthenticated()]
    return super().get_permissions()

  @action(detail=True, methods=['GET'])
  def users(self, request, pk=None):
    """
    Returns a list of all users in the organization.
    Only accessible by Org Staff.
    """
    organization = self.get_object()
    
    # Permission check (already handled by OrganizationPermissions for GET, but double check logic)
    # OrganizationPermissions: GET -> superuser or (isOrgStaff and org==obj)
    # So self.get_object() will raise 403 if not allowed.
    
    users = User.objects.filter(profile__organization=organization)
    serializer = UserSerializer(users, many=True, context={'request': request})
    return Response(serializer.data)

  @action(detail=True, methods=['POST'])
  def verify_user(self, request, pk=None):
    """
    Approve or Decline a pending user.
    Payload: { 'user_email': '...', 'action': 'approve' | 'decline' }
    """
    organization = self.get_object()
    
    # Additional explicit check: requester must be Org Staff
    if not (request.user.is_superuser or (request.user.profile.isOrgStaff and request.user.profile.organization == organization)):
        return returnForbidden()

    email = request.data.get('user_email')
    action_type = request.data.get('action')
    
    if not email or not action_type:
        return Response({'error': 'Missing user_email or action'}, status=status.HTTP_400_BAD_REQUEST)
        
    try:
        user = User.objects.get(email=email, profile__organization=organization)
    except User.DoesNotExist:
        return returnNotFound('User not found in this organization')
        
    if action_type == 'approve':
        user.profile.pendingValidation = False
        user.profile.save()
        return Response({'status': 'approved'})
        
    elif action_type == 'decline':
        # Delete user if declined (assuming they are new/pending)
        user.delete()
        return Response({'status': 'declined'})
        
    return Response({'error': 'Invalid action'}, status=status.HTTP_400_BAD_REQUEST)

  @action(detail=True, methods=['POST'])
  def promote_staff(self, request, pk=None):
    """
    Promote a user to Organization Staff.
    Payload: { 'user_email': '...' }
    """
    organization = self.get_object()
    
    if not (request.user.is_superuser or (request.user.profile.isOrgStaff and request.user.profile.organization == organization)):
        return returnForbidden()
        
    email = request.data.get('user_email')
    if not email:
         return Response({'error': 'Missing user_email'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        user = User.objects.get(email=email, profile__organization=organization)
    except User.DoesNotExist:
        return returnNotFound('User not found in this organization')
        
    user.profile.isOrgStaff = True
    user.profile.save()
    
    return Response({'status': 'promoted'})

  @action(detail=True, methods=['POST'])
  def demote_staff(self, request, pk=None):
    """
    Demote a user from Organization Staff.
    Payload: { 'user_email': '...' }
    """
    organization = self.get_object()
    
    if not (request.user.is_superuser or (request.user.profile.isOrgStaff and request.user.profile.organization == organization)):
        return returnForbidden()
        
    email = request.data.get('user_email')
    if not email:
         return Response({'error': 'Missing user_email'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        user = User.objects.get(email=email, profile__organization=organization)
    except User.DoesNotExist:
        return returnNotFound('User not found in this organization')
        
    # Prevent self-demotion? optional but good UX. 
    if user == request.user:
        return Response({'error': 'You cannot demote yourself'}, status=status.HTTP_400_BAD_REQUEST)

    user.profile.isOrgStaff = False
    user.profile.save()
    
    return Response({'status': 'demoted'})

  @action(detail=True, methods=['POST'])
  def remove_user(self, request, pk=None):
    """
    Remove a user from the organization.
    Payload: { 'user_email': '...' }
    """
    organization = self.get_object()
    
    if not (request.user.is_superuser or (request.user.profile.isOrgStaff and request.user.profile.organization == organization)):
        return returnForbidden()
        
    email = request.data.get('user_email')
    if not email:
         return Response({'error': 'Missing user_email'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        user = User.objects.get(email=email, profile__organization=organization)
    except User.DoesNotExist:
        return returnNotFound('User not found in this organization')
        
    # Prevent self-removal
    if user == request.user:
        return Response({'error': 'You cannot remove yourself'}, status=status.HTTP_400_BAD_REQUEST)

    user.profile.organization = None
    user.profile.isOrgStaff = False
    user.profile.save()
    
    return Response({'status': 'removed'})

  @action(detail=True, methods=['POST'])
  def reset_user_password(self, request, pk=None):
    """
    Send password reset email to a user.
    Payload: { 'user_email': '...' }
    """
    from django.contrib.auth.tokens import default_token_generator
    from core.emails import PasswordResetEmail
    
    organization = self.get_object()
    
    if organization.sso_enabled:
        return Response({'error': 'Cannot reset password for SSO-enabled organization'}, status=status.HTTP_400_BAD_REQUEST)
    
    if not (request.user.is_superuser or (request.user.profile.isOrgStaff and request.user.profile.organization == organization)):
        return returnForbidden()
        
    email = request.data.get('user_email')
    if not email:
         return Response({'error': 'Missing user_email'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        user = User.objects.get(email=email, profile__organization=organization)
    except User.DoesNotExist:
        return returnNotFound('User not found in this organization')
    
    # Send password reset email
    try:
        reset_email = PasswordResetEmail(user)
        reset_email.send()
        return Response({'status': 'reset_email_sent'})
    except Exception as e:
        return Response({'error': f'Failed to send email: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

  @action(detail=True, methods=['GET'])
  def analytics(self, request, pk=None):
    """
    Returns analytics for the organization.
    """
    from django.utils import timezone
    from datetime import timedelta
    from core.models import Course, Submission, Assignment
    
    organization = self.get_object()
    
    # Get all users in org
    total_users = User.objects.filter(profile__organization=organization).count()
    
    # Active users (logged in within last 30 days)
    thirty_days_ago = timezone.now() - timedelta(days=30)
    active_users = User.objects.filter(
        profile__organization=organization,
        last_login__gte=thirty_days_ago
    ).count()
    
    # Courses
    total_courses = Course.objects.filter(organization=organization).count()
    active_courses = Course.objects.filter(organization=organization, archived=False).count()
    
    # Assignments
    org_courses = Course.objects.filter(organization=organization)
    total_assignments = Assignment.objects.filter(course__in=org_courses).count()

    # Submissions
    total_submissions = Submission.objects.filter(assignment__course__in=org_courses).count()
    submissions_this_month = Submission.objects.filter(
        assignment__course__in=org_courses,
        created__gte=thirty_days_ago
    ).count()
    
    return Response({
        'total_users': total_users,
        'active_users': active_users,
        'total_courses': total_courses,
        'active_courses': active_courses,
        'total_assignments': total_assignments,
        'total_submissions': total_submissions,
        'submissions_this_month': submissions_this_month,
    })
