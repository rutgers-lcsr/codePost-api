from django.http import HttpResponseRedirect
from django.contrib.auth.models import User
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from core.serializers.user import UserSerializer
from django.utils.timezone import now
from django.contrib.auth.models import update_last_login
from rest_framework_simplejwt import serializers, views
from rest_framework_simplejwt.views import TokenRefreshSlidingView


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
  def get_token(cls, user):
      token = super().get_token(user)
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

