from datetime import timedelta
from django.http import HttpResponseRedirect
from django.contrib.auth.models import User
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
import logging
from drf_spectacular.utils import extend_schema
from core.logging import logEvent
from core.models import Course, OneTimeToken
from core.serializers.user import UserSerializer
from django.utils.timezone import now
from django.contrib.auth.models import update_last_login
from rest_framework_simplejwt import serializers, views
from rest_framework_simplejwt.views import TokenRefreshSlidingView
from core.forms.forms import ImpersonateForm
from codepost.settings import DEBUG
from core.serializers.auth import (
  GenerateOTTRequestSerializer,
  GenerateOTTResponseSerializer,
  ValidateOTTRequestSerializer,
  JwtOttResponseSerializer,
)
@extend_schema(responses={200: UserSerializer})
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def current_user(request):
  """
  Determine the current user by their token, and return their data
  """
  serializer = UserSerializer(request.user, context={'request': request})

  token = JWTSerializer.get_token(request.user)
  data = serializer.data
  data['token'] = str(token)
  return Response(data)

# Plan to update this to Pair with the new JWTSerializer
class JWTSerializer(serializers.TokenObtainSlidingSerializer):
  
  @classmethod
  def one_time_token(cls, user):
      token = super().get_token(user)
      token.set_exp(lifetime=timedelta(minutes=5))
      token['user_id'] = user.id
      token['email'] = user.email
      token['username'] = user.username
      return token
  
  @classmethod
  def get_token(cls, user, never_expire=False):
     
      token = super().get_token(user)
      if never_expire:
          # Set the token to never expire
          token.set_exp(lifetime=timedelta(days=365 * 1))
      token['user_id'] = user.id
      token['email'] = user.email
      token['username'] = user.username
      return token
  def validate(self, attrs):
    data = super().validate(attrs)
    
    self.context['request'].user = self.user
    # raise Exception(f"{self.user} {self.user.profile}")
    data['user'] = UserSerializer(self.user, context=self.context).data
    data['user']['token'] = data['token']

    update_last_login(None, self.user)
    return data


class AccountLoginAPIView(views.TokenObtainSlidingView):
  
  serializer_class = JWTSerializer

obtain_jwt_token = AccountLoginAPIView.as_view()


class ImpersonateView(APIView):
  """
  View to handle impersonation of users.
  """
  permission_classes = [IsAuthenticated]
  
  def post(self, request, *args, **kwargs):

    form = ImpersonateForm(request.data)
    if not form.is_valid():
      return Response({"error": form.errors}, status=400)

    username = form.cleaned_data.get('username')

    # Check if the becomee user exists
    try:
      user = User.objects.get(username=username, is_active=True)
    except User.DoesNotExist:
      return Response({"error": "User does not exist"}, status=404)
    
    # Ensure the requestee user is a course admin and that target user is a student/grader
    sharded_course = Course.objects.filter(courseAdmins=request.user, students=user) | Course.objects.filter(courseAdmins=request.user, graders=user)
    if not sharded_course.exists():
      return Response({"error": "You do not have permission to impersonate this user."}, status=403)

    # if never_expire is set, we will set the token to expire in 1 year
    should_expire = form.cleaned_data.get('never_expire', False) == True
    
    # Log the impersonation event
    logEvent(
        event="Become User",
        message=f"User {request.user.username} is becoming {user.username}",
        level=logging.INFO
    )
    
    # Set the user in the request
    request.user = user


    # Generate a token for the user
    token = JWTSerializer.get_token(request.user, never_expire=should_expire)
    serializer = UserSerializer(request.user, context={'request': request})

    data = serializer.data
    data['token'] = str(token)

    update_last_login(None, user)
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

  sharded_course = Course.objects.filter(
      Q(courseAdmins=request.user) &
      (
          Q(students=user) |
          Q(graders=user) |
          Q(courseAdmins=user)
      )
  )

  if not sharded_course.exists() and not request.user.username == username:
    return Response({"error": "You do not have permission to generate a one-time token for this user."}, status=403)

  
  # Log the event
  logEvent(
      event="Generate One-Time Token",
      message=f"User {request.user.username} is generating a one-time token for {user.username}, from {request.META.get('REMOTE_ADDR', 'unknown')}, {request.META.get('HTTP_USER_AGENT', 'unknown')}",
      level=logging.INFO
  )

  # remove previous tokens
  OneTimeToken.objects.filter(user=user).delete()
  
  token = OneTimeToken.objects.create(user=user)
  return Response({
    "token": str(token.token),
    "expires_at": token.expires_at.isoformat()
  })
  
  
@extend_schema(request=ValidateOTTRequestSerializer, responses={200: UserSerializer})
@api_view(['GET', 'POST'])
@permission_classes([])
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

  jwt_token = JWTSerializer.get_token(user, never_expire=True)

  data = serializer.data
  data['token'] = str(jwt_token)
  
  update_last_login(None, user)
  
  return Response(data)

@extend_schema(responses={200: JwtOttResponseSerializer})
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_jwt_ott(request):
  """
  Generate a JWT short-lived 5 min token for the authenticated user.
  Used to exchange a one-time token for imbedding in an iframe or other uses.
  """
  token = JWTSerializer.one_time_token(request.user)
  return Response({
    "token": str(token),
    "expires_at": token['exp']
  })