# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from django.contrib.auth.models import User
from core.models import Organization

# Create superuser
james = User.objects.create(username="james@example.com", email="james@example.com")
james.is_superuser = True
james.set_password('rootabega')
james.save()

## Create an organization, course, and assignment
princeton = Organization.objects.create(name="Princeton University", shortname="Princeton")

## Create admins
for i in range(0, 2):
  username = "admin" + str(i) + "@princeton.edu"
  tmpUser = User.objects.create(username=username, email=username, password="rootabega")
  tmpUser.profile.organization = princeton
  tmpUser.set_password("rootabega")
  tmpUser.save()

## Create graders
for i in range(0, 3):
  username = "grader" + str(i) + "@princeton.edu"
  tmpUser = User.objects.create(username=username, email=username, password="rootabega")
  tmpUser.profile.organization = princeton
  tmpUser.set_password("rootabega")
  tmpUser.save()

## Create students
for i in range(0, 10):
  username = "student" + str(i) + "@princeton.edu"
  tmpUser = User.objects.create(username=username, email=username, password="rootabega")
  tmpUser.profile.organization = princeton
  tmpUser.set_password("rootabega")
  tmpUser.save()

## Create an organization, course, and assignment
yale = Organization.objects.create(name="Yale University", shortname="Yale")

## Create admins
for i in range(0, 1):
  username = "admin" + str(i) + "@yale.edu"
  tmpUser = User.objects.create(username=username, email=username, password="rootabega")
  tmpUser.profile.organization = yale
  tmpUser.set_password("rootabega")
  tmpUser.save()

## Create graders
for i in range(0, 1):
  username = "grader" + str(i) + "@yale.edu"
  tmpUser = User.objects.create(username=username, email=username, password="rootabega")
  tmpUser.profile.organization = princeton
  tmpUser.set_password("rootabega")
  tmpUser.save()

## Create students
for i in range(0, 1):
  username = "student" + str(i) + "@yale.edu"
  tmpUser = User.objects.create(username=username, email=username, password="rootabega")
  tmpUser.profile.organization = princeton
  tmpUser.set_password("rootabega")
  tmpUser.save()