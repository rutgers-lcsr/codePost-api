# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from datetime import timedelta
from core.models import User
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import api_view, authentication_classes, permission_classes, throttle_classes
from rest_framework.authentication import BasicAuthentication, SessionAuthentication, TokenAuthentication
from core.authentication import CourseScopedJWTAuthentication
from rest_framework.response import Response
from rest_framework.views import APIView
import logging
from drf_spectacular.utils import extend_schema
from core.logging import logEvent
from core.models import Course, OneTimeToken
from core.serializers.user import UserSerializer
from django.contrib.auth.models import update_last_login
from rest_framework_simplejwt import serializers, views
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken
from codepost.settings import DEBUG
from core.throttles import AuthAnonRateThrottle, AuthUserRateThrottle
from core.serializers.auth import (
  GenerateOTTRequestSerializer,
  GenerateOTTResponseSerializer,
  ValidateOTTRequestSerializer,
  ExchangeOTTRequestSerializer,
  ExchangeOTTResponseSerializer,
  JwtOttResponseSerializer,
  ImpersonateRequestSerializer,
  LogoutRequestSerializer,
  LogoutResponseSerializer,
)
from rest_framework_simplejwt.exceptions import TokenError
# Authentication classes that exclude CourseAPIKeyAuthentication.
# Used on endpoints that issue unscoped tokens (current_user, get_jwt_ott,
# token-auth, token-refresh) to prevent a course key holder from obtaining
# a token with broader access than the key itself grants.
NON_COURSE_KEY_AUTH = (
    TokenAuthentication,
    CourseScopedJWTAuthentication,
    BasicAuthentication,
    SessionAuthentication,
)


# ---------------------------------------------------------------------------
# Token issuance helpers (access + refresh model)
#
# The access token is the short-lived credential sent on every request. The
# refresh token (long-lived) is exchanged at /token-refresh/ for a new access
# token; rotation blacklists the old refresh token (see SIMPLE_JWT settings).
# ---------------------------------------------------------------------------

def _apply_claims(token, user, course_id=None):
  """Attach codePost's custom claims to a token (access or refresh)."""
  token['user_id'] = user.id
  token['email'] = user.email
  token['username'] = user.username
  if course_id is not None:
    token['course_id'] = course_id


def tokens_for_user(user, *, course_id=None):
  """Issue an (access, refresh) pair for an interactive browser session.

  Uses ``RefreshToken.for_user`` which, with the token_blacklist app installed,
  records an OutstandingToken so the session can later be revoked. Custom claims
  set on the refresh token are copied onto the derived access token.
  """
  refresh = RefreshToken.for_user(user)
  _apply_claims(refresh, user, course_id)
  return str(refresh.access_token), str(refresh)


def _access_token_obj(user, *, course_id=None, lifetime=None):
  """Build a standalone AccessToken (no refresh token, no OutstandingToken row).

  Used for embedded/machine tokens that are consumed directly as Bearer
  credentials and are never refreshed: the token embedded in every user
  serialization, the 5-minute iframe token, long-lived Jupyter/OTT tokens, the
  SSO redirect token, and never-expire impersonation tokens.
  """
  access = AccessToken.for_user(user)
  _apply_claims(access, user, course_id)
  if lifetime is not None:
    access.set_exp(lifetime=lifetime)
  return access


def access_token_for_user(user, *, course_id=None, lifetime=None):
  """String form of :func:`_access_token_obj`."""
  return str(_access_token_obj(user, course_id=course_id, lifetime=lifetime))


@extend_schema(responses={200: UserSerializer})
@api_view(['GET'])
@authentication_classes(NON_COURSE_KEY_AUTH)
@permission_classes([IsAuthenticated])
def current_user(request):
  """
  Determine the current user by their token, and return their data.

  Returns a fresh access token (as ``token``) plus a ``refresh`` token. This is
  also how an SSO session (which only receives an access token via the redirect
  URL) obtains its refresh token, without ever putting the refresh token in a URL.
  """
  serializer = UserSerializer(request.user, context={'request': request})

  access, refresh = tokens_for_user(request.user)
  data = serializer.data
  data['token'] = access
  data['refresh'] = refresh
  return Response(data)


class JWTSerializer(serializers.TokenObtainPairSerializer):
  """Password-login serializer issuing an access + refresh pair.

  Extends the standard pair serializer to attach codePost's custom claims and to
  embed the serialized user (and a backward-compatible ``token`` alias for the
  access token) in the response.
  """

  @classmethod
  def get_token(cls, user):
    token = super().get_token(user)  # RefreshToken; claims copy to access token
    _apply_claims(token, user)
    return token

  def validate(self, attrs):
    data = super().validate(attrs)  # {'access': ..., 'refresh': ...}

    self.context['request'].user = self.user
    # Backward-compatible alias: existing clients read `token` as the credential.
    data['token'] = data['access']  # type: ignore[index]  # dict-like access on ReturnDict
    data['user'] = UserSerializer(self.user, context=self.context).data  # type: ignore[assignment]  # JWT token data dict
    data['user']['token'] = data['access']  # type: ignore[index]  # dict-like access on ReturnDict

    update_last_login(None, self.user)  # type: ignore[arg-type]  # Django stubs expect _UserModel sender
    return data


class AccountLoginAPIView(views.TokenObtainPairView):
  serializer_class = JWTSerializer
  throttle_classes = [AuthAnonRateThrottle]

obtain_jwt_token = AccountLoginAPIView.as_view()


class ImpersonateView(APIView):
  """
  View to handle impersonation of users.
  Accepts either 'username' (exact match) or 'email' (lookup by email) in the POST body.
  Staff/superusers can impersonate any user. Course admins can only impersonate
  students or graders in courses they administer.
  """
  permission_classes = [IsAuthenticated]
  throttle_classes = [AuthUserRateThrottle]

  @extend_schema(request=ImpersonateRequestSerializer, responses={200: UserSerializer})
  def post(self, request, *args, **kwargs):

    username = (request.data.get('username') or '').strip()
    email = (request.data.get('email') or '').strip()

    if not username and not email:
      return Response({"error": "Either 'username' or 'email' is required."}, status=400)

    # Resolve the target user
    try:
      if username:
        user = User.objects.get(username=username, is_active=True)
      else:
        user = User.objects.get(email=email, is_active=True)
    except User.DoesNotExist:
      return Response({"error": "User does not exist"}, status=404)
    
    # Determine if the request is course-scoped (via course API key or scoped JWT)
    course_scope_id = getattr(request, 'course_scope_id', None)
    if course_scope_id is None:
      auth = getattr(request, 'auth', None)
      if isinstance(auth, dict):
        course_scope_id = auth.get('course_scope_id')
      elif hasattr(auth, 'course_scope_id'):
        course_scope_id = auth.course_scope_id

    # Authorization: staff/superusers can impersonate anyone.
    # Course admins can only impersonate students/graders in their courses.
    # Course-scoped requests can only impersonate members of the scoped course.
    if course_scope_id is not None:
      from core.permissions.helpers import isCourseMember
      try:
        scoped_course = Course.objects.get(pk=course_scope_id)
      except Course.DoesNotExist:
        return Response({"error": "Scoped course does not exist."}, status=400)
      if not isCourseMember(user, scoped_course):
        return Response({"error": "Target user is not a member of the scoped course."}, status=403)
    elif not (request.user.is_staff or request.user.is_superuser):
      sharded_course = Course.objects.filter(courseAdmins=request.user, students=user) | Course.objects.filter(courseAdmins=request.user, graders=user)
      if not sharded_course.exists():
        return Response({"error": "You do not have permission to impersonate this user."}, status=403)

    # Only superusers can create long-lived impersonation tokens
    should_expire = request.data.get('never_expire', False) and request.user.is_superuser
    
    # Log the impersonation event
    logEvent(
        event="Become User",
        message=f"User {request.user.username} is becoming {user.username}",
        level=logging.INFO,
        event_type='audit'
    )
    
    # Set the user in the request
    request.user = user


    # Generate a token for the user — propagate course scope if present.
    serializer = UserSerializer(request.user, context={'request': request})
    data = serializer.data
    if should_expire:
      # Superuser long-lived impersonation token (used directly, not refreshed).
      data['token'] = access_token_for_user(request.user, course_id=course_scope_id, lifetime=timedelta(days=365))
    else:
      # Interactive impersonation session — issue a refreshable pair.
      access, refresh = tokens_for_user(request.user, course_id=course_scope_id)
      data['token'] = access
      data['refresh'] = refresh

    update_last_login(None, user)  # type: ignore[arg-type]  # Django stubs expect _UserModel sender
    return Response(data)



@extend_schema(
  request=GenerateOTTRequestSerializer,
  responses={200: GenerateOTTResponseSerializer}
)
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def generate_one_time_token(request):
  """
  Generate a one-time token for the authenticated course instructor. 
  
  Used to create one time tokens for jupyter servers.
  """
  params = request.query_params
  # Invalidate previous tokens
  username = params.get('username') or request.data.get('username')
  if not username:
    return Response({"error": "username query parameter is required"}, status=400)
  
  # Remove leading and trailing whitespace
  username = username.strip()
  
  # Check if the becomee user exists
  try:
    user = User.objects.get(username=username, is_active=True)
  except User.DoesNotExist:
    return Response({"error": "User does not exist"}, status=404)
  
  # Ensure the requestee user is a course admin and that target user is a student/grader/instructor
  from django.db.models import Q

  # Use chained .filter() calls so Django creates separate M2M JOINs.
  # A single filter(Q(courseAdmins=request.user) & Q(courseAdmins=user)) would
  # resolve both lookups to the same JOIN alias, making the AND impossible when
  # request.user != user.
  sharded_course = Course.objects.filter(courseAdmins=request.user).filter(
      Q(students=user) |
      Q(graders=user) |
      Q(courseAdmins=user)
  )

  if not sharded_course.exists() and not request.user.username == username:
    return Response({"error": "You do not have permission to generate a one-time token for this user."}, status=403)

  
  # Log the event
  logEvent(
      event="Generate One-Time Token",
      message=f"User {request.user.username} is generating a one-time token for {user.username}, from {request.META.get('REMOTE_ADDR', 'unknown')}, {request.META.get('HTTP_USER_AGENT', 'unknown')}",
      level=logging.INFO,
      event_type='audit'
  )

  # Determine if the request is course-scoped (CourseKey or course-scoped JWT).
  course_scope_id = getattr(request, 'course_scope_id', None)
  if course_scope_id is None:
    auth = getattr(request, 'auth', None)
    if isinstance(auth, dict):
      course_scope_id = auth.get('course_scope_id')
    elif hasattr(auth, 'course_scope_id'):
      course_scope_id = auth.course_scope_id

  # remove previous tokens
  OneTimeToken.objects.filter(user=user).delete()
  
  create_kwargs = {'user': user}
  if course_scope_id is not None:
    create_kwargs['course_id'] = course_scope_id

  token = OneTimeToken.objects.create(**create_kwargs)
  return Response({
    "token": str(token.token),
    "expires_at": token.expires_at.isoformat()
  })
  
  
@extend_schema(request=ValidateOTTRequestSerializer, responses={200: UserSerializer})
@api_view(['GET', 'POST'])
@permission_classes([])
@throttle_classes([AuthAnonRateThrottle])
def validate_one_time_token(request):
  """
  Validate a one-time token and return the associated user data. 
  
  Used for long lived Jupyter server sessions. Should stay in memory. 
  """
  params = request.query_params
  token_str = params.get('token') or request.data.get('token')
  if not token_str:
    return Response({"error": "token query parameter is required"}, status=400)
  
  try:
    token_obj = OneTimeToken.objects.get(token=token_str)
  except OneTimeToken.DoesNotExist:
    return Response({"error": "Invalid token"}, status=404)
  
  if not DEBUG and not token_obj.is_valid():
    return Response({"error": "Token has expired or already used"}, status=400)
  
  # Mark the token as used
  if not DEBUG:
    # allow re-use in debug mode
    token_obj.used = True
    token_obj.save()
  
  user = token_obj.user
  request.user = user
  serializer = UserSerializer(user, context={'request': request})

  # Propagate course scope from the OTT into the JWT. Jupyter servers hold this
  # token for a long-lived session and consume it directly (never refreshed), so
  # issue a long-lived standalone access token.
  ott_course_id = token_obj.course_id if token_obj.course_id else None
  data = serializer.data
  data['token'] = access_token_for_user(user, course_id=ott_course_id, lifetime=timedelta(days=365))
  
  update_last_login(None, user)  # type: ignore[arg-type]  # Django stubs expect _UserModel sender
  
  return Response(data)

@extend_schema(request=ExchangeOTTRequestSerializer, responses={200: ExchangeOTTResponseSerializer})
@api_view(['POST'])
@permission_classes([])
@throttle_classes([AuthAnonRateThrottle])
def exchange_one_time_token(request):
  """
  Consume a one-time token and issue a normal interactive access + refresh pair.

  Used by the Safe Exam Browser launch flow: SEB opens a fresh browser session with no
  stored auth, so the launch URL carries an OTT that this endpoint exchanges for the
  same short-lived, rotating session a login would issue. Deliberately NOT
  /ott/validate/, which issues a 365-day standalone token for long-lived Jupyter
  servers — the wrong risk profile for a student quiz session.
  """
  token_str = request.data.get('token')
  if not token_str:
    return Response({"error": "token is required"}, status=400)

  try:
    token_obj = OneTimeToken.objects.get(token=token_str)
  except OneTimeToken.DoesNotExist:
    return Response({"error": "Invalid token"}, status=404)

  if not token_obj.is_valid():
    return Response({"error": "Token has expired or already used"}, status=400)

  # Single-use, even in DEBUG: a reusable token in a URL is a session-hijack vector.
  token_obj.used = True
  token_obj.save()

  user = token_obj.user
  access, refresh = tokens_for_user(user, course_id=token_obj.course_id)
  update_last_login(None, user)  # type: ignore[arg-type]  # Django stubs expect _UserModel sender
  return Response({"token": access, "refresh": refresh})


@extend_schema(responses={200: JwtOttResponseSerializer})
@api_view(['GET'])
@authentication_classes(NON_COURSE_KEY_AUTH)
@permission_classes([IsAuthenticated])
def get_jwt_ott(request):
  """
  Generate a JWT short-lived 5 min token for the authenticated user.
  Used to exchange a one-time token for imbedding in an iframe or other uses.
  """
  token = _access_token_obj(request.user, lifetime=timedelta(minutes=5))
  return Response({
    "token": str(token),
    "expires_at": token['exp']
  })


@extend_schema(request=LogoutRequestSerializer, responses={200: LogoutResponseSerializer})
@api_view(['POST'])
@authentication_classes(NON_COURSE_KEY_AUTH)
@permission_classes([IsAuthenticated])
def logout(request):
  """
  Revoke a single session by blacklisting its refresh token.

  Idempotent: an already-blacklisted, expired, or malformed token still returns
  200 so the client can proceed to clear local state and redirect to login.
  """
  refresh = request.data.get('refresh')
  if refresh:
    try:
      RefreshToken(refresh).blacklist()
    except TokenError:
      # Already blacklisted / expired / invalid — nothing more to revoke.
      pass
  return Response({"detail": "Logged out."})


@extend_schema(request=None, responses={200: LogoutResponseSerializer})
@api_view(['POST'])
@authentication_classes(NON_COURSE_KEY_AUTH)
@permission_classes([IsAuthenticated])
def logout_all(request):
  """
  Revoke every session for the authenticated user ("log out everywhere") by
  blacklisting all of their outstanding refresh tokens.
  """
  from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken

  tokens = OutstandingToken.objects.filter(user=request.user)
  for token in tokens:
    BlacklistedToken.objects.get_or_create(token=token)
  return Response({"detail": "All sessions revoked."})