from rest_framework import serializers
from core.serializers.template import ModelSerializerWithPOSTCheck
from core.serializers.course import CourseSerializer
from core.serializers.section import SectionSerializer
from rest_framework_simplejwt.settings import api_settings
from core.models import User, Organization, Profile
from rest_framework.authtoken.models import Token


# Helpful source: https://medium.com/@dakota.lillie/django-react-jwt-authentication-5015ee00ef9a
class UserSerializer(ModelSerializerWithPOSTCheck):
  organization = serializers.CharField(source="profile.organization.name", required=False, default='no organization set')
  api_token = serializers.PrimaryKeyRelatedField(source="profile.api_token", queryset=Token.objects.all())
  token = serializers.SerializerMethodField()
  password = serializers.CharField(write_only=True)
  studentCourses = serializers.SerializerMethodField()
  hasCredentials = serializers.SerializerMethodField()
  graderCourses = CourseSerializer(many=True, source="grader_courses")
  superGraderCourses = CourseSerializer(many=True, source="superGrader_courses")
  courseadminCourses = CourseSerializer(many=True, source="courseAdmin_courses")
  leaderSections = SectionSerializer(many=True, source="leader_sections")
  codePostAdmin = serializers.SerializerMethodField()
  hasCredentials = serializers.SerializerMethodField()

  canCreateCourses = serializers.BooleanField(source="profile.canCreateCourses")
  canModifyRosters = serializers.BooleanField(source="profile.canModifyRosters")
  showProductTips = serializers.BooleanField(source="profile.showProductTips")

  class Meta:
    model = User
    fields = ('id', 'token', 'email', 'password', 'organization', 'studentCourses', 'graderCourses', 'superGraderCourses', 'courseadminCourses', 'leaderSections', 'codePostAdmin', 'canCreateCourses', 'canModifyRosters', 'showProductTips', 'api_token', 'student_sections', 'hasCredentials')
    POST_permissions_fields = ()
    extra_field_kwargs = {'url': {'lookup_field': 'email'}}
    read_only_fields = ('codePostAdmin',)

  # defining this as a SerializerMethodField so we can pass the request context into the CourseSerializer
  def get_studentCourses(self, obj):
    return CourseSerializer(list(obj.student_courses.all()), many=True, context={"request": self.context['request']}).data

  def get_hasCredentials(self, obj):
    if obj.password and obj.has_usable_password():
      return True
    return False

  def get_token(self, obj):
    jwt_payload_handler = api_settings.JWT_PAYLOAD_HANDLER
    jwt_encode_handler = api_settings.JWT_ENCODE_HANDLER

    payload = jwt_payload_handler(obj)
    token = jwt_encode_handler(payload)
    return token

  def create(self, validated_data):
    # Extract parameters that can't be used in User constructor
    profile = validated_data.pop('profile')
    password = validated_data.pop('password', None)

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

  def get_codePostAdmin(self, obj):
    return obj.is_superuser
