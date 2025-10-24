import pytz

from rest_framework import serializers
from core.serializers.template import ModelSerializerWithPOSTCheck
from core.models import Submission, User
from core.serializers.file import FileSerializer, SubmissionFileSerializer
from core.serializers.submissionTest import SubmissionTestSerializer
from core.permissions.helpers import isStudent, isGrader, should_use_student_captions
from datetime import timezone


def formErrorMessage(message, users):
  toRet = message + ": "
  for user in users:
    toRet = toRet + user.email + ", "
  return toRet[:-2]


class SubmissionSerializerWithoutFiles(ModelSerializerWithPOSTCheck):
  dateEdited = serializers.SerializerMethodField()

  students = serializers.SlugRelatedField(many=True, slug_field='email', queryset=User.objects.all(), allow_null=True)

  grader = serializers.SlugRelatedField(many=False, slug_field='email',
                                        queryset=User.objects.all(), required=False, allow_null=True)

  questionResponder = serializers.SlugRelatedField(
      many=False, slug_field='email', queryset=User.objects.all(), required=False, allow_null=True)

  class Meta:
    model = Submission
    fields = ('id', 'assignment', 'students', 'grader', 'isFinalized', 'dateEdited', 'grade', 'queueOrderKey', 'dateUploaded',
              'questionIsOpen', 'questionIsRegrade', 'questionText', 'questionResponder', 'questionResponse', 'questionDate', 'responseDate', 'tests', 'testRunsCompleted', 'lateDayCreditsUsed',)
    read_only_fields = ('dateEdited', 'grade', 'questionText', 'questionDate',
                        'responseDate', 'tests', 'testRunsCompleted')
    POST_permissions_fields = ('assignment',)

  def get_dateEdited(self, obj):
    tz = pytz.timezone(obj.assignment.course.timezone)
    return obj.dateEdited.astimezone(tz)

  def to_representation(self, obj):
    ret = super().to_representation(obj)
    course = obj.assignment.course

    if 'request' in self.context and should_use_student_captions(self.context['request'].user, course):
        caption_map = course.studentCaptions
        ret['students'] = list(map(lambda x: caption_map[x.email] if x.email in caption_map else x.email, obj.students.all()))
    return ret

class SubmissionSerializer(SubmissionSerializerWithoutFiles):
  # Explicitly use SubmissionFileSerializer for the files relationship
  files = SubmissionFileSerializer(many=True, read_only=True)

  class Meta(SubmissionSerializerWithoutFiles.Meta):
    fields = SubmissionSerializerWithoutFiles.Meta.fields + ('files',)
    read_only_fields = SubmissionSerializerWithoutFiles.Meta.read_only_fields + ('files',)

  def update(self, instance, validated_data):
    if instance.grader and ('grader' in validated_data and validated_data['grader'] is None):
      if self.context['request'].user == instance.grader:
        # The above defines an unclaim condition / operation
        if 'queueOrderKey' not in validated_data:
          if instance.assignment.course.sendReleasedSubmissionsToBack:
            biggestKey = Submission.objects.filter(assignment=instance.assignment).order_by(
                '-queueOrderKey')[0].queueOrderKey + 1
            validated_data['queueOrderKey'] = biggestKey

    return super().update(instance, validated_data)

  def get_dateEdited(self, obj):
    tz = pytz.timezone(obj.assignment.course.timezone)
    return obj.dateEdited.astimezone(tz)

  # We can't use validate_students, because we need information from the assignment (the course)
  # Note that we're not checking permissions here, though we could...
  # To consider: validate by request type here
  # Pros: more self-documenting (permissions sit with objects)
  def validate(self, data):
    newData = super().validate(data)
    newFields = self.genProposedFields(newData)

    # This might change if the assignment is changed (of course, the requesting user must have the
    # appropriate permissions for the new course to which they are trying to assign this submission).
    course = newFields['assignment'].course

    # Check that the specified students belong to the submission's course
    badList = []
    for student in newFields['students']:
      if not isStudent(student, course):  # can't add student who is not in the course.
        if not self.instance or (student not in self.instance.students.all()):
          badList.append(student)
    if len(badList) > 0:
      message = formErrorMessage("The following students are not members of the specified course", badList)
      raise serializers.ValidationError(message)

    # Check that the list of students is not empty
    if len(newFields['students']) == 0:
      message = "The students list cannot be empty."
      raise serializers.ValidationError(message)

    # # Check that students are not already tied to other submissions in this course
    badList = []
    # newFields['students'] could be null
    for student in newFields['students']:
      otherSubs = Submission.objects.filter(assignment=newFields['assignment'], students__in=[student])
      if len(otherSubs) > 1 or (len(otherSubs) == 1 and not self.instance):
        badList.append(student)
    if len(badList) > 0:
      message = formErrorMessage("The following students already have submissions for this assignment", badList)
      raise serializers.ValidationError(message)

    # Check that the specified grader belongs to the relevant course
    if 'grader' in newFields and newFields['grader'] and not isGrader(newFields['grader'], course):
      raise serializers.ValidationError(newFields['grader'].email + " is not a grader of the specified course.")

    # Check that if isFinalized == true, throw an error if grader or grade is null
    if newFields['isFinalized']:
      if newFields['grader'] is None:
        raise serializers.ValidationError("Finalized submission must have a grader.")

    # Check that at least one student on the submission has enough Late Day Credits left
    if course.lateDayCreditsAllowable != None and newFields['lateDayCreditsUsed'] != None and newFields['lateDayCreditsUsed'] > 0:
      atLeastOneStudentHasEnoughLateDayCredits = False
      for student in newFields['students']:
        thisCourseSubmissions = Submission.objects.filter(assignment__course=course, students__in=[student])

        totaLateDayCreditsUsed = 0
        for submission in thisCourseSubmissions:
          if submission.id != newFields['id']:
            totaLateDayCreditsUsed += submission.lateDayCreditsUsed

        if totaLateDayCreditsUsed + newFields['lateDayCreditsUsed'] <= course.lateDayCreditsAllowable:
          atLeastOneStudentHasEnoughLateDayCredits = True

      if not atLeastOneStudentHasEnoughLateDayCredits:
        raise serializers.ValidationError(
            "None of the submission students have enough late day credits remaining for the course.")

    return newData


class AnonymousSubmissionSerializer(serializers.ModelSerializer):
  # Explicitly use SubmissionFileSerializer for the files relationship
  files = SubmissionFileSerializer(many=True, read_only=True)
  grader = serializers.SlugRelatedField(many=False, slug_field='email', queryset=User.objects.all())
  questionResponder = serializers.SlugRelatedField(
      many=False, slug_field='email', queryset=User.objects.all(), required=False, allow_null=True)

  class Meta:
    model = Submission

    fields = ('id', 'assignment', 'grader', 'isFinalized', 'dateEdited', 'grade', 'files', 'queueOrderKey', 'dateUploaded', 'questionIsOpen',
              'questionIsRegrade', 'questionText', 'questionResponder', 'questionResponse', 'questionDate', 'responseDate', 'tests', 'testRunsCompleted', 'lateDayCreditsUsed')
    read_only_fields = ('id', 'assignment', 'files',
                        'questionText', 'questionDate', 'responseDate', 'tests', 'testRunsCompleted')


class SubmissionStatusSerializer(serializers.ModelSerializer):
  students = serializers.SlugRelatedField(many=True, slug_field='email', queryset=User.objects.all())
  hasGrader = serializers.SerializerMethodField()
  questionResponder = serializers.SlugRelatedField(
      many=False, slug_field='email', queryset=User.objects.all(), required=False, allow_null=True)

  def get_hasGrader(self, obj):
    return obj.grader != None

  class Meta:
    model = Submission
    fields = ('id', 'assignment', 'students', 'isFinalized', 'questionIsOpen', 'questionIsRegrade', 'questionText',
              'questionResponder', 'questionResponse', 'questionDate', 'responseDate', 'dateUploaded', 'hasGrader', 'testRunsCompleted', 'lateDayCreditsUsed')
    read_only_fields = ('id', 'assignment', 'students', 'isFinalized', 'questionIsOpen', 'questionIsRegrade', 'questionText',
                        'questionResponder', 'questionResponse', 'questionDate', 'responseDate', 'dateUploaded', 'hasGrader', 'testRunsCompleted', 'lateDayCreditsUsed')

class StudentSubmissionSerializer(serializers.ModelSerializer):
  # Explicitly use SubmissionFileSerializer for the files relationship
  files = SubmissionFileSerializer(many=True, read_only=True)
  students = serializers.SlugRelatedField(many=True, slug_field='email', queryset=User.objects.all())
  questionResponder = serializers.SlugRelatedField(
      many=False, slug_field='email', queryset=User.objects.all(), required=False, allow_null=True)

  class Meta:
    model = Submission
    fields = ('id', 'assignment', 'students', 'isFinalized', 'files', 'grade', 'questionIsOpen', 'questionIsRegrade',
              'questionText', 'questionResponder', 'questionResponse', 'questionDate', 'responseDate', 'dateUploaded', 'tests', 'testRunsCompleted', 'lateDayCreditsUsed')
    read_only_fields = ('id', 'assignment', 'students', 'isFinalized', 'files', 'grade', 'questionIsOpen', 'questionIsRegrade',
                        'questionText', 'questionResponder', 'questionResponse', 'questionDate', 'responseDate', 'dateUploaded', 'tests', 'testRunsCompleted', 'lateDayCreditsUsed')

class StudentSubmissionWithoutGradeSerializer(serializers.ModelSerializer):
  # Explicitly use SubmissionFileSerializer for the files relationship
  files = SubmissionFileSerializer(many=True, read_only=True)
  students = serializers.SlugRelatedField(many=True, slug_field='email', queryset=User.objects.all())
  questionResponder = serializers.SlugRelatedField(
      many=False, slug_field='email', queryset=User.objects.all(), required=False, allow_null=True)

  class Meta:
    model = Submission
    fields = ('id', 'assignment', 'students', 'isFinalized', 'files', 'questionIsOpen', 'questionIsRegrade',
              'questionText', 'questionResponder', 'questionResponse', 'questionDate', 'responseDate', 'dateUploaded', 'tests', 'testRunsCompleted', 'lateDayCreditsUsed')
    read_only_fields = ('id', 'assignment', 'students', 'isFinalized', 'files', 'questionIsOpen', 'questionIsRegrade',
                        'questionText', 'questionResponder', 'questionResponse', 'questionDate', 'responseDate', 'dateUploaded', 'tests', 'testRunsCompleted', 'lateDayCreditsUsed')

# This is a light-weight serializer to return submission tests
class SubmissionWithTestsSerializer(serializers.ModelSerializer):
  tests = SubmissionTestSerializer(many=True)

  class Meta:
    model = Submission
    fields = ('id', 'tests', )
    read_only_fields = ('id', 'tests',)
