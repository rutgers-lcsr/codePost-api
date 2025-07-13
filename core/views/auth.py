from django.http import HttpResponseRedirect
from django.contrib.auth.models import User
from rest_framework import permissions, status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.views import APIView
from core.serializers.user import UserSerializer
from django.utils.timezone import now

from django.contrib.auth.models import update_last_login
from rest_framework_simplejwt import serializers, views


@api_view(['GET'])
def current_user(request):
  """
  Determine the current user by their token, and return their data
  """

  if request.user:
    # user = request.user
    # user.last_login = now()
    # user.save(update_fields=['last_login'])
    serializer = UserSerializer(request.user, context={'request': request})
    return Response(serializer.data)
  else:
    return Response([])


class JWTSerializer(serializers.TokenObtainPairSerializer):
  def validate(self, attrs):
    validated_data = super().validate(attrs)
    update_last_login(None, validated_data['user'])
    return validated_data


class AccountLoginAPIView(views.TokenObtainPairView):
  
  serializer_class = JWTSerializer

obtain_jwt_token = AccountLoginAPIView.as_view()