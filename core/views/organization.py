# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
import logging

from core.models import Organization
from core.serializers.organization import OrganizationSerializer
from core.views.template import SuperUserListProtectedViewSet
from rest_framework.permissions import IsAuthenticated
from core.permissions.permissions import OrganizationPermissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from core.models import User
from core.serializers.user import UserSerializer
from core.permissions.helpers import returnForbidden, returnNotFound
from drf_spectacular.utils import extend_schema, OpenApiParameter
from core.serializers.ai_usage import (
    OrganizationAISettingsSerializer,
    OrganizationAISettingsUpdateSerializer,
    AIUsageSummarySerializer,
    AIProviderModelsListSerializer,
    AIProviderTestRequestSerializer,
    AIProviderTestResultSerializer,
)
from core.throttles import AIConnectionTestThrottle

logger = logging.getLogger(__name__)



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
    if self.action in ['verify_user', 'promote_staff', 'demote_staff', 'remove_user', 'reset_user_password', 'analytics', 'aiSettings', 'aiUsage', 'aiModels', 'aiTest', 'pending_admins', 'approve_admin', 'deny_admin']:
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

  @action(detail=True, methods=['GET'])
  def pending_admins(self, request, pk=None):
    """
    Returns a list of users with pendingValidation=True in this organization.
    Only accessible by Org Staff or superuser.
    """
    organization = self.get_object()

    if not (request.user.is_superuser or (request.user.profile.isOrgStaff and request.user.profile.organization == organization)):
        return returnForbidden()

    pending_users = User.objects.filter(
        profile__organization=organization,
        profile__pendingValidation=True
    )
    serializer = UserSerializer(pending_users, many=True, context={'request': request})
    return Response(serializer.data)

  @action(detail=True, methods=['POST'])
  def approve_admin(self, request, pk=None):
    """
    Approve a pending admin request. Grants canCreateCourses=True.
    Payload: { 'user_email': '...' }
    """
    from core.emails import NewAdminActivationEmail

    organization = self.get_object()

    if not (request.user.is_superuser or (request.user.profile.isOrgStaff and request.user.profile.organization == organization)):
        return returnForbidden()

    email = request.data.get('user_email')
    if not email:
        return Response({'error': 'Missing user_email'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        user = User.objects.get(email=email, profile__organization=organization, profile__pendingValidation=True)
    except User.DoesNotExist:
        return returnNotFound('Pending user not found in this organization')

    user.profile.pendingValidation = False
    user.profile.canCreateCourses = True
    user.profile.canModifyRosters = True
    user.is_active = True
    user.save()
    user.profile.save()

    # Send activation email to the user
    NewAdminActivationEmail(user=user).send_email(organization_name=organization.name)

    logger.info(f"Admin approved: {email} for org {organization.name} by {request.user.email}")

    return Response({'status': 'approved'})

  @action(detail=True, methods=['POST'])
  def deny_admin(self, request, pk=None):
    """
    Deny a pending admin request.
    Payload: { 'user_email': '...' }
    """
    from core.utils import is_course_member
    from log.models import Event

    organization = self.get_object()

    if not (request.user.is_superuser or (request.user.profile.isOrgStaff and request.user.profile.organization == organization)):
        return returnForbidden()

    email = request.data.get('user_email')
    if not email:
        return Response({'error': 'Missing user_email'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        user = User.objects.get(email=email, profile__organization=organization, profile__pendingValidation=True)
    except User.DoesNotExist:
        return returnNotFound('Pending user not found in this organization')

    user.profile.pendingValidation = False
    user.profile.save()

    Event.objects.create(
        category="registration",
        user=str(user),
        description="Admin request denied",
    )

    logger.info(f"Admin denied: {email} for org {organization.name} by {request.user.email}")

    # If user has no course memberships, delete them
    if not is_course_member(user):
        user.delete()
        return Response({'status': 'denied_and_deleted'})

    return Response({'status': 'denied'})

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
        user.profile.canCreateCourses = True
        user.profile.canModifyRosters = True
        user.is_active = True
        user.save()
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
        reset_email.send_email()
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

  @extend_schema(
    request=OrganizationAISettingsUpdateSerializer,
    responses=OrganizationAISettingsSerializer,
  )
  @action(detail=True, methods=['GET', 'PATCH'])
  def aiSettings(self, request, pk=None):
    """
    GET: Return the organization's AI configuration.
    PATCH: Update the organization's AI configuration.
    Only accessible by Org Staff or superuser.
    """
    organization = self.get_object()

    if not (request.user.is_superuser or (request.user.profile.isOrgStaff and request.user.profile.organization == organization)):
        return returnForbidden()

    if request.method == 'GET':
        serializer = OrganizationAISettingsSerializer(organization, context={'request': request})
        return Response(serializer.data)

    serializer = OrganizationAISettingsUpdateSerializer(
        organization, data=request.data, partial=True, context={'request': request}
    )
    serializer.is_valid(raise_exception=True)
    serializer.save()
    # Return full read serializer
    read_serializer = OrganizationAISettingsSerializer(organization, context={'request': request})
    return Response(read_serializer.data)

  @extend_schema(
    responses=AIProviderModelsListSerializer,
  )
  @action(detail=True, methods=['GET'])
  def aiModels(self, request, pk=None):
    """
    GET: Return curated AI models for the org's configured provider.
    Also queries the provider's API for live model listings using the org's stored credentials.
    Only accessible by Org Staff or superuser.
    """
    import asyncio
    from core.services.ai_service import AI_MODELS, list_provider_models

    organization = self.get_object()

    if not (request.user.is_superuser or (request.user.profile.isOrgStaff and request.user.profile.organization == organization)):
        return returnForbidden()

    provider = organization.ai_provider
    if not provider:
        return Response({'providers': []})

    # Build curated list
    curated = AI_MODELS.get(provider, [])
    result = {
        'provider': provider,
        'models': [
            {'id': mid, 'name': name, 'isDefault': default}
            for mid, name, default in curated
        ],
    }

    # Query provider for live models
    try:
        live = asyncio.run(list_provider_models(
            provider=provider,
            api_key=organization.ai_api_key or '',
            base_url=organization.ai_base_url or '',
        ))
        result['liveModels'] = live
    except Exception as e:
        logger.warning(f"Failed to list models from {provider}: {e}")
        result['liveError'] = str(e)

    return Response({'providers': [result]})

  @extend_schema(request=AIProviderTestRequestSerializer, responses={200: AIProviderTestResultSerializer})
  @action(detail=True, methods=['POST'], throttle_classes=[AIConnectionTestThrottle])
  def aiTest(self, request, pk=None):
    """
    POST: Fire a small completion through the org's stored AI config and
    report success, latency, and any error. Accepts an optional custom
    prompt and a one-off model override. Recorded in AI usage as
    'provider_test'. Only accessible by Org Staff or superuser.
    """
    import asyncio
    from core.services.ai_service import AIService, GenerationResult

    organization = self.get_object()

    if not (request.user.is_superuser or (request.user.profile.isOrgStaff and request.user.profile.organization == organization)):
        return returnForbidden()

    body = AIProviderTestRequestSerializer(data=request.data)
    body.is_valid(raise_exception=True)

    svc = AIService.for_config(
        provider=organization.ai_provider or '',
        api_key=organization.ai_api_key or '',
        base_url=organization.ai_base_url or '',
        model=organization.ai_model or '',
    ).set_request_context(user=request.user, request_type='provider_test')
    result = asyncio.run(svc.test_connection(
        prompt=body.validated_data.get('prompt') or None,
        model=body.validated_data.get('model') or None,
    ))

    # Record usage when a request was actually attempted (sync context —
    # record_usage does ORM work that can't run inside asyncio.run).
    if result.get('requestSystemPrompt') is not None:
        svc.record_usage(
            GenerationResult(
                text=result.get('response') or '',
                success=result['success'],
                error=result.get('error'),
                input_tokens=result.get('_inputTokens', 0),
                output_tokens=result.get('_outputTokens', 0),
                total_tokens=result.get('_totalTokens', 0),
                cached_tokens=result.get('_cachedTokens', 0),
            ),
            request.user,
            request_type='provider_test',
            organization=organization,
        )

    return Response(AIProviderTestResultSerializer(result).data)

  @extend_schema(
    responses=AIUsageSummarySerializer,
    parameters=[
        OpenApiParameter(name='granularity', required=False, type=str,
                         description="Time bucket granularity: 'hourly', 'daily', or 'monthly'",
                         enum=['hourly', 'daily', 'monthly']),
        OpenApiParameter(name='startDate', required=False, type=str,
                         description="Start date (ISO 8601)"),
        OpenApiParameter(name='endDate', required=False, type=str,
                         description="End date (ISO 8601)"),
    ],
  )
  @action(detail=True, methods=['GET'])
  def aiUsage(self, request, pk=None):
    """
    Returns AI usage analytics for the organization.
    Includes time-series data and per-course breakdown.
    Only accessible by Org Staff or superuser.
    """
    organization = self.get_object()

    if not (request.user.is_superuser or (request.user.profile.isOrgStaff and request.user.profile.organization == organization)):
        return returnForbidden()

    from core.services.ai_usage_analytics import get_usage_summary
    from core.services.ai_service import AIService
    from core.models import AIUsageRecord
    from django.utils.dateparse import parse_datetime

    granularity = request.query_params.get('granularity', 'daily')
    if granularity not in ('hourly', 'daily', 'monthly'):
        granularity = 'daily'

    start_date = None
    end_date = None
    start_str = request.query_params.get('startDate', '').strip()
    end_str = request.query_params.get('endDate', '').strip()
    if start_str:
        start_date = parse_datetime(start_str)
    if end_str:
        end_date = parse_datetime(end_str)

    queryset = AIUsageRecord.objects.filter(organization=organization)

    summary = get_usage_summary(
        queryset=queryset,
        granularity=granularity,
        start_date=start_date,
        end_date=end_date,
        breakdown_field='course',
        breakdown_name_field='course__name',
        breakdown_extra_fields=['course__period'],
        breakdown_name_formatter=lambda entry: (
            f"{entry['course__name'] or 'Unknown'} ({entry['course__period']})"
            if entry.get('course__period')
            else entry['course__name'] or 'Unknown'
        ),
        projection_rates=AIService.merged_token_rates(organization=organization),
    )

    return Response(summary)
