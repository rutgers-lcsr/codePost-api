# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from core.serializers.template import ModelSerializerWithPOSTCheck
from core.serializers.course import CourseSerializer
from core.serializers.section import SectionSerializer
from core.models import User, Organization, Profile
from rest_framework.authtoken.models import Token


# Helpful source: https://medium.com/@dakota.lillie/django-react-jwt-authentication-5015ee00ef9a
class UserSerializer(ModelSerializerWithPOSTCheck):
  organization = serializers.PrimaryKeyRelatedField(source="profile.organization", queryset=Organization.objects.all(), required=False, allow_null=True)
  api_token = serializers.PrimaryKeyRelatedField(source="profile.api_token", queryset=Token.objects.all(), required=False, allow_null=True)
  password = serializers.CharField(write_only=True)
  studentCourses = serializers.SerializerMethodField()
  hasCredentials = serializers.SerializerMethodField()
  graderCourses = CourseSerializer(many=True, source="grader_courses")
  superGraderCourses = CourseSerializer(many=True, source="superGrader_courses")
  courseadminCourses = CourseSerializer(many=True, source="courseAdmin_courses")
  leaderSections = SectionSerializer(many=True, source="leader_sections")
  codePostAdmin = serializers.BooleanField(source="is_superuser", required=False)
  hasCredentials = serializers.SerializerMethodField()

  canCreateCourses = serializers.BooleanField(source="profile.canCreateCourses")
  canModifyRosters = serializers.BooleanField(source="profile.canModifyRosters")
  isOrgStaff = serializers.BooleanField(source="profile.isOrgStaff", required=False)
  showProductTips = serializers.BooleanField(source="profile.showProductTips")
  token = serializers.SerializerMethodField()
  
  class Meta:
    model = User
    fields = ('id', 'email', 'password', 'organization', 'studentCourses', 'graderCourses', 'superGraderCourses', 
              'courseadminCourses', 'leaderSections', 'codePostAdmin', 'canCreateCourses', 'canModifyRosters', 
              'isOrgStaff', 'showProductTips', 'api_token', 'student_sections', 'hasCredentials', 'token')
    POST_permissions_fields = ()
    extra_field_kwargs = {'url': {'lookup_field': 'email'}}
    read_only_fields = ()
    ordering = ('email',)

  # defining this as a SerializerMethodField so we can pass the request context into the CourseSerializer
  @extend_schema_field(CourseSerializer(many=True))
  def get_studentCourses(self, obj):
    request = self.context.get('request', None)
    return CourseSerializer(list(obj.student_courses.all()), many=True, context={"request": request}).data

  @extend_schema_field(serializers.BooleanField)
  def get_hasCredentials(self, obj):
    if obj.password and obj.has_usable_password():
      return True
    return False

  @extend_schema_field(serializers.CharField(allow_null=True))
  def get_token(self, obj):
    from core.views.auth import access_token_for_user

    # check if user is authenticated or admin
    request = self.context.get('request', None)
    if not request or not request.user.is_authenticated:
      return None

    # do not return token if the requestor is not the user themselves or a superuser
    user = self.context.get('request').user  # type: ignore[union-attr]  # request always present
    if not user.is_authenticated:
      return None
    if not (user.is_superuser or user.id == obj.id):
      return None
    # Access token only: this runs on every user serialization, so it must not
    # mint a refresh token or write an OutstandingToken row.
    return access_token_for_user(obj)
  
  def create(self, validated_data):
    # Extract parameters that can't be used in User constructor
    profile = validated_data.pop('profile')
    password = validated_data.pop('password', None)
    
    # Pop nested fields that are not handled by default create
    validated_data.pop('grader_courses', None)
    validated_data.pop('superGrader_courses', None)
    validated_data.pop('courseAdmin_courses', None)
    validated_data.pop('leader_sections', None)
    
    # We simply ignore them for now as we are just creating the user/student
    # If we needed to set them, we would do it after creation.

    # Create object
    validated_data['username'] = validated_data['email']
    obj = super().create(validated_data)

    # Set organization on profile
    obj.profile.organization = profile["organization"]

    # Set password
    if password is not None:
      obj.set_password(password)

    obj.save()
    return obj

  def update(self, instance, validated_data):
    profile_data = validated_data.pop('profile', {})
    
    # Update User instance
    for attr, value in validated_data.items():
      if attr == 'password':
        instance.set_password(value)
      else:
        setattr(instance, attr, value)
    instance.save()

    profile_data = validated_data.pop('profile', {})
    
    # Explicitly handle isOrgStaff if it appears in root validated_data
    # This happens because source='profile.isOrgStaff' might not nest it automatically in all DRF versions/configs
    if 'isOrgStaff' in validated_data:
        profile_data['isOrgStaff'] = validated_data.pop('isOrgStaff')

    # Update User instance
    for attr, value in validated_data.items():
      if attr == 'password':
        instance.set_password(value)
      else:
        setattr(instance, attr, value)
    instance.save()

    # Update Profile instance
    profile = instance.profile
    for attr, value in profile_data.items():
      setattr(profile, attr, value)
    profile.save()

    return instance

  def get_profile(self, obj):
    try:
      return obj.profile
    except (AttributeError, Profile.DoesNotExist):
      # Create profile if it doesn't exist
      profile, created = Profile.objects.get_or_create(user=obj)
      return profile


class LightUserSerializer(serializers.ModelSerializer):
  """
  Minimal user serializer for list views - no nested objects to avoid N+1 queries.
  """
  organization = serializers.PrimaryKeyRelatedField(source="profile.organization", read_only=True)
  codePostAdmin = serializers.BooleanField(source="is_superuser", read_only=True)
  isOrgStaff = serializers.BooleanField(source="profile.isOrgStaff", read_only=True)
  pendingValidation = serializers.BooleanField(source="profile.pendingValidation", read_only=True)
  hasCredentials = serializers.SerializerMethodField()

  class Meta:
    model = User
    fields = ('id', 'email', 'organization', 'codePostAdmin', 'isOrgStaff', 'pendingValidation', 
              'hasCredentials', 'is_active', 'date_joined', 'last_login')
    read_only_fields = fields

  @extend_schema_field(serializers.BooleanField)
  def get_hasCredentials(self, obj):
    if obj.password and obj.has_usable_password():
      return True
    return False
