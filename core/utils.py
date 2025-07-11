from core.serializers.user import UserSerializer
from core.models import Assignment, RubricCategory, Environment, TestCategory
from django.template import loader
from django.core.mail import EmailMultiAlternatives

from django.contrib.auth.tokens import default_token_generator
from django.contrib.sites.shortcuts import get_current_site
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_text
from django.core.exceptions import ObjectDoesNotExist
from django.contrib.auth.models import User
from rest_framework.response import Response
from rest_framework import status
from django import forms

from django.contrib.auth.forms import PasswordResetForm, SetPasswordForm

from mooc.models import Product

import re

def my_jwt_response_handler(token, user=None, request=None):

  # if we don't do this, then the UserSerializer won't be able to access the requesting user.
  # why? because the *request to authenticate* doesn't contain an authenticated user
  request.user = user

  return {
      'token': token,
      'user': UserSerializer(user, context={'request': request}).data
  }

def is_course_member(user):
  if len(user.student_courses.all()) > 0:
    return True

  if len(user.grader_courses.all()) > 0:
    return True

  if len(user.courseAdmin_courses.all()) > 0:
    return True

  if len(user.student_inactive_courses.all()) > 0:
    return True

  if len(user.grader_inactive_courses.all()) > 0:
    return True

  if len(user.courseAdmin_inactive_courses.all()) > 0:
    return True

  return False


def is_email(email):
  if len(email) > 7:
    if re.match(r"[^@]+@[^@]+\.[^@]+", email):
      return True
  return False


def email_passes_whitelist(email, whitelist):
  if len(whitelist) == 0:
    return True

  valid_domains = whitelist.split("\n")
  email_domain = email.split('@')[1]
  for domain in valid_domains:
    if domain == email_domain:
      return True

  return False

def get_or_create_user(email, organization):
  """ If a user corresponds to <email>, return that user. Else,
  create a user with <email> and set their organization to <organization> """

  if is_email(email):
    try:
      thisUser = User.objects.get(email=email)
      return thisUser
    except:
      newUser = User.objects.create(username=email, email=email, is_active=False)
      newUser.profile.organization = organization
      newUser.save()
      return newUser
  else:
    return None


def send_mail(subject_template_name, email_template_name,
              context, from_email, to_email, html_email_template_name=None):
  """
  Send a django.core.mail.EmailMultiAlternatives to `to_email`.
  """
  subject = loader.render_to_string(subject_template_name, context)
  subject = ''.join(subject.splitlines())
  body = loader.render_to_string(email_template_name, context)

  email_message = EmailMultiAlternatives(subject, body, from_email, [to_email])
  if html_email_template_name is not None:
    html_email = loader.render_to_string(html_email_template_name, context)
    email_message.attach_alternative(html_email, 'text/html')

  print(email_message)
  email_message.send()


def domain_from_email(email):
  return '@' + email.split('@')[1]


def get_mooc_courses():
  courses = list(Product.objects.values_list('course', flat=True))
  return courses

def copy_assignment(assignment, destination_course):
  new_assignment = assignment
  original_assignment = Assignment.objects.get(id=assignment.id)

  course_assignments = Assignment.objects.filter(course=destination_course.id).values_list('name', flat=True)
  count = 1
  new_name = "{} (copy {})".format(new_assignment.name, count)

  # Prevent copying the same assignment into the same course more than 10 times
  while new_name in course_assignments and count < 10:
      count += 1
      new_name = "{} (copy {})".format(new_assignment.name, count)

  if count == 10:
      return None

  # copy assignment
  new_assignment.id = None
  new_assignment.pk = None
  new_assignment.name = new_name
  new_assignment.course_id = destination_course.id
  new_assignment.save()


  # copy rubric
  for rubricCategory in original_assignment.rubricCategories.all():
      original_rubricCategory = RubricCategory.objects.get(id=rubricCategory.id)
      rubricCategory.id = None
      rubricCategory.pk = None
      rubricCategory.assignment_id = new_assignment.id
      rubricCategory.save()
      for rubricComment in original_rubricCategory.rubricComments.all():
          rubricComment.id = None
          rubricComment.pk = None
          rubricComment.category_id = rubricCategory.id
          rubricComment.save()

  # copy tests
  for testCategory in original_assignment.testCategories.all():
      original_testCategory = TestCategory.objects.get(id=testCategory.id)
      testCategory.id = None
      testCategory.pk = None
      testCategory.assignment_id = new_assignment.id
      testCategory.save()
      for testCase in original_testCategory.testCases.all():
          testCase.id = None
          testCase.pk = None
          testCase.testCategory_id = testCategory.id
          testCase.save()

  try:
      environment = original_assignment.environment
  except ObjectDoesNotExist:
      environment = None

  if environment is not None:
      original_environment = Environment.objects.get(id=environment.id)
      environment.id = None
      environment.pk = None
      environment.assignment_id = new_assignment.id
      environment.save()

      for solutionFile in original_environment.solutionFiles.all():
          solutionFile.id = None
          solutionFile.pk = None
          solutionFile.environment_id = environment.id
          solutionFile.save()

      for helperFile in original_environment.helperFiles.all():
          helperFile.id = None
          helperFile.pk = None
          helperFile.environment_id = environment.id
          helperFile.save()

      for sourceFile in original_environment.sourceFiles.all():
          sourceFile.id = None
          sourceFile.pk = None
          sourceFile.environment_id = environment.id
          sourceFile.save()

  return new_assignment

