# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from rest_framework import serializers



class ModelSerializerWithPOSTCheck(serializers.ModelSerializer):

  def createForPOSTCheck(self):
    '''
    Use the POST_permissions_fields field to infer which fields are required for permissions
    checking. If POST_permissions_fields not present, default to using all of the provided data.
    '''
    thisModel = getattr(self.Meta, 'model', None)
    POST_permissions_fields = getattr(self.Meta, 'POST_permissions_fields', None)
    if POST_permissions_fields is not None:
      forConstructor = {}
      for field_name in POST_permissions_fields:
        forConstructor[field_name] = self.validated_data[field_name]
      return thisModel(**forConstructor)  # type: ignore[reportOptionalCall]

    return thisModel(**self.validated_data)  # type: ignore[reportOptionalCall]

  def genProposedFields(self, data):
    toRet = {}
    fields = getattr(self.Meta, 'fields', None) or []
    for field in fields:
      if field in data:
        toRet[field] = data[field]
      elif self.instance:
        fieldObject = getattr(self.instance, field, None)

        # An example of a field defined in an object's serializer but not the object instance is a calculated field
        # Calculated fields are by definition read_only

        # Note: probably should just ignore all fields marked as read-only by default
        # But this check will gracefully handle situations in which a calculated field is declared
        # but left out of the read_only_fields tuple
        if fieldObject is not None:
          # If the object is a many to many or one to many object, use .all() so it returns an iterable
          if fieldObject.__class__.__name__ == 'ManyRelatedManager' or fieldObject.__class__.__name__ == 'RelatedManager':
            toRet[field] = fieldObject.all()
          else:
            toRet[field] = fieldObject
      else:
        toRet[field] = None

    return toRet

  def assert_authoring_course(self, course):
    '''
    Guard cross-course reassignment. Object permissions authorize against the *source*
    object's course, but a writable ``course``/``quiz``/``bank`` FK can relocate a resource
    (or point it at another course's data) into ``course``. Require the destination course
    to be unarchived (the base validate() only checks the *source* course's archived flag)
    and the acting user to have quiz-authoring rights (course staff or superuser) there too.
    No-op when there is no request/user in context (internal, non-request writes).
    '''
    from core.permissions.helpers import isCourseStaff
    if course is None:
      return
    # Mirrors the source-course check in validate(): no superuser exemption.
    if course.archived:
      raise serializers.ValidationError("The Course is archived and cannot be edited.")
    request = self.context.get('request')
    user = getattr(request, 'user', None)
    if user is None:
      return
    if user.is_superuser or isCourseStaff(user, course):
      return
    from rest_framework.exceptions import PermissionDenied
    raise PermissionDenied("You do not have authoring access to the destination course.")

  def validate(self, data):
    try:
      course = self.instance.course  # type: ignore[union-attr]  # instance always set during validate
    except:
      course = None

    if self.instance.__class__.__name__ != 'Course' and course is not None and course.archived:
      raise serializers.ValidationError("The Course is archived and cannot be edited.")

    return super().validate(data)

