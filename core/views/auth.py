from datetime import timedelta
from django.http import HttpResponseRedirect
from django.contrib.auth.models import User
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from core.models import Course
from core.serializers.user import UserSerializer
from django.utils.timezone import now
from django.contrib.auth.models import update_last_login
from rest_framework_simplejwt import serializers, views
from rest_framework_simplejwt.views import TokenRefreshSlidingView
from core.forms.forms import ImpersonateForm

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

    try:
      user = User.objects.get(username=username)
    except User.DoesNotExist:
      return Response({"error": "User does not exist"}, status=404)
    
    # Ensure the user is a course admin and that target user is a student/grader
    sharded_course = Course.objects.filter(courseAdmins=request.user, students=user) | Course.objects.filter(courseAdmins=request.user, graders=user)
    if not sharded_course.exists():
      return Response({"error": "You do not have permission to impersonate this user."}, status=403)

    should_expire = form.cleaned_data.get('never_expire', False)
    # Set the user in the request
    request.user = user    

    
    # Generate a token for the user
    token = JWTSerializer.get_token(request.user, never_expire=should_expire)
    serializer = UserSerializer(request.user, context={'request': request})

    data = serializer.data
    data['token'] = str(token)

    update_last_login(None, user)
    return Response(data)
