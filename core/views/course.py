# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from core.forms.forms import IDForm
from core.models import Course, RubricCategory
from django.contrib.auth.models import User
from core.serializers.course import (
    CourseSerializer,
    CourseRosterSerializer,
    CourseSettingsSerializer,
    CourseAISettingsSerializer,
    CourseRosterMapSerializer,
    CourseStudentCaptionsSerializer,
)
from core.serializers.section import SectionSerializer
from core.serializers.user import UserSerializer
from core.views.template import SuperUserListProtectedViewSet

from rest_framework.response import Response
from rest_framework.decorators import action
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from rest_framework.permissions import IsAuthenticated
from rest_framework import serializers
from rest_framework import status

from core.permissions.permissions import CoursePermissions
from core.permissions.helpers import (
    returnNotAuthorized,
    returnForbidden,
    returnNotFound,
)
from core.permissions.helpers import isAuthenticated
from core.permissions.helpers import isStudent, isGrader, isCourseAdmin, isCourseMember, isCourseStaff
from core.permissions.helpers import isStudentOfSub, isStaffOfSub, isSuperGrader
from core.serializers.ai_usage import AIUsageSummarySerializer

from core.pagination import LargeObjectsPagination

from django.contrib.auth.tokens import default_token_generator

from core.utils import get_or_create_user

# Can override get_serializer method to use different serializer for
# different user types
from core.emails import UserAddedToCourseEmail

def generate_invite_code():
    import secrets
    import string

    # methodology: https://stackoverflow.com/a/23728630
    return "".join(
        secrets.choice(string.ascii_uppercase + string.digits) for _ in range(10)
    )


class CourseViewSet(SuperUserListProtectedViewSet):
    """
    list:
    Return a list of all the courses.

    create:
    Create a new course.

    retrieve:
    Return the given course.

    update:
    Update a course.

    partial_update:
    Update a course.

    delete:
    Delete a course
    """

    queryset = Course.objects.all()
    serializer_class = CourseSerializer
    permission_classes = (IsAuthenticated, CoursePermissions)

    def list(self, request):
        user = request.user

        if not isAuthenticated(user):
            return returnNotAuthorized()

        courses = user.courseAdmin_courses.all()
        if user.profile.isOrgStaff:
            courses = courses | Course.objects.filter(organization=user.profile.organization)
            courses = courses.distinct()

        return Response(
            CourseSerializer(
                courses, many=True, context={"request": request}
            ).data
        )

    @extend_schema(responses=CourseSettingsSerializer)
    @action(detail=True, methods=["GET", "PATCH"])
    def courseSettings(self, request, pk=None):
        user = request.user
        if not isAuthenticated(user):
            return returnNotAuthorized()

        course = self.get_object()

        if not isCourseMember(user, course):
            return returnForbidden()

        if request.method == "GET":
            serializer = CourseSettingsSerializer(course, context={"request": request})
            return Response(serializer.data)
        elif request.method == "PATCH":
            if not isCourseAdmin(user, course):
                return returnForbidden()

        serializer = CourseSettingsSerializer(
            course, data=request.data, partial=True, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(serializer.data)

    @extend_schema(responses=OpenApiTypes.STR)
    @action(detail=True, methods=["PATCH"])
    def changeInviteCode(self, request, pk=None):
        user = request.user
        if not isAuthenticated(user):
            return returnNotAuthorized()

        course = self.get_object()
        if not isCourseAdmin(user, course):
            return returnForbidden()

        course.inviteCode = generate_invite_code()
        course.save()

        return Response(course.inviteCode)

    @extend_schema(request=CourseAISettingsSerializer, responses=CourseAISettingsSerializer)
    @action(detail=True, methods=["GET", "PATCH"])
    def aiSettings(self, request, pk=None):
        """
        get:
        Get AI configuration for the course.

        patch:
        Update AI configuration for the course. Admin-only.
        """
        user = request.user
        if not isAuthenticated(user):
            return returnNotAuthorized()

        course = self.get_object()

        if request.method == "GET":
            if not isCourseStaff(user, course):
                return returnForbidden()
        else:
            if not isCourseAdmin(user, course):
                return returnForbidden()

        if request.method == "GET":
            serializer = CourseAISettingsSerializer(course, context={"request": request})
            return Response(serializer.data)
        elif request.method == "PATCH":
            serializer = CourseAISettingsSerializer(
                course, data=request.data, partial=True, context={"request": request}
            )
            serializer.is_valid(raise_exception=True)
            self.perform_update(serializer)
            return Response(serializer.data)

    @extend_schema(
        responses={200: AIUsageSummarySerializer},
        parameters=[
            OpenApiParameter(name='granularity', required=False, type=str,
                             description="Time bucket granularity: 'hourly', 'daily', or 'monthly'",
                             enum=['hourly', 'daily', 'monthly']),
            OpenApiParameter(name='startDate', required=False, type=str,
                             description="Start date (ISO 8601)"),
            OpenApiParameter(name='endDate', required=False, type=str,
                             description="End date (ISO 8601)"),
        ],
    )
    @action(detail=True, methods=["GET"])
    def aiUsage(self, request, pk=None):
        """
        Returns AI usage analytics for the course.
        Includes time-series data and per-assignment breakdown.
        Only accessible by course admins.
        """
        user = request.user
        if not isAuthenticated(user):
            return returnNotAuthorized()

        course = self.get_object()

        if not isCourseAdmin(user, course):
            return returnForbidden()

        from core.services.ai_usage_analytics import get_usage_summary
        from core.models import AIUsageRecord
        from django.utils.dateparse import parse_datetime

        granularity = request.query_params.get('granularity', 'daily')
        if granularity not in ('hourly', 'daily', 'monthly'):
            granularity = 'daily'

        start_date = None
        end_date = None
        start_str = request.query_params.get('startDate', '').strip()
        end_str = request.query_params.get('endDate', '').strip()
        if start_str:
            start_date = parse_datetime(start_str)
        if end_str:
            end_date = parse_datetime(end_str)

        queryset = AIUsageRecord.objects.filter(course=course)

        summary = get_usage_summary(
            queryset=queryset,
            granularity=granularity,
            start_date=start_date,
            end_date=end_date,
            breakdown_field='assignment',
            breakdown_name_field='assignment__name',
        )

        return Response(summary)

    @extend_schema(responses=CourseRosterSerializer)
    @action(detail=True, methods=["GET", "PATCH"])
    def roster(self, request, pk=None):
        """
        get:
        Show the roster for a course.

        patch:
        Update the roster for a course.
        """
        user = request.user
        course = self.get_object()

        error = get_roster_permission_errors(user, request, course)
        if error:
            return error

        if request.method == "GET":
            serializer = CourseRosterSerializer(course, context={"request": request})
            return Response(serializer.data)

        elif request.method == "PATCH":
            # Pre-filter fields for any users who do not exist yet
            # Create these users so serializer doesn't raise a DoesNotExist
            # error for any of them
            tempCreated: list[User] = []
            for keyEl in ["students", "graders", "courseAdmins"]:
                # Since these users are being created via the SDK, assume they should be active
                parse_new_users(keyEl, request, tempCreated, auto_activate=True)

            # Log for emailing new students
            oldStudents = list(course.students.all())
            oldGraders = list(course.graders.all())
            oldAdmins = list(course.courseAdmins.all())

            serializer = CourseRosterSerializer(
                course, data=request.data, partial=True, context={"request": request}
            )
            if serializer.is_valid():
                self.perform_update(serializer)

                # Add elevated permissions to courseAdmins
                newAdmins = course.courseAdmins.all()
                for admin in newAdmins:
                    if admin not in oldAdmins:
                        # Permissions model: once a user is added as a courseadmin to (any) course, they unlock the ability to create courses
                        # and modify rosters.
                        add_admin_privileges(admin)

                # If course setting is set, email newly created users
                if course.emailNewUsers:
                    # Email new students
                    for keyEl in ["students", "graders", "courseAdmins"]:
                        if keyEl in request.data:
                            if keyEl == "students":
                                oldList = oldStudents
                                newList = course.students.all()
                                roleType = "student"
                            elif keyEl == "graders":
                                oldList = oldGraders
                                newList = course.graders.all()
                                roleType = "grader"
                            elif keyEl == "courseAdmins":
                                oldList = oldAdmins
                                newList = course.courseAdmins.all()
                                roleType = "admin"

                            for userInRoster in newList:
                                if userInRoster not in oldList:
                                    UserAddedToCourseEmail(userInRoster).send_email(
                                        course_name=course.name,
                                        course_period=course.period,
                                        user_type=roleType,
                                        force_send=True
                                    )
                                    # send_new_user_email(userInRoster, roleType, course)

                from webhooks.signals import hook_event

                for keyEl in ["students", "graders", "courseAdmins"]:
                    """
                    Roster webhooks
                    > course.courseAdmins
                    > course.graders
                    > course.students

                    Webhook triggers with new users added to the 'extra' field in the payload
                    """
                    if keyEl in request.data:
                        if keyEl == "students":
                            oldList = oldStudents
                            newList = course.students.all()
                            roleType = "student"
                        elif keyEl == "graders":
                            oldList = oldGraders
                            newList = course.graders.all()
                            roleType = "grader"
                        elif keyEl == "courseAdmins":
                            oldList = oldAdmins
                            newList = course.courseAdmins.all()
                            roleType = "admin"

                        hook_event.send(
                            sender=course.__class__,
                            action="roster",
                            instance=course,
                            updated_fields=[keyEl],
                            payload_addition=list(
                                newList.exclude(
                                    email__in=map(lambda u: u.email, oldList)
                                )
                            ),
                        )

            else:
                # If something went wrong, delete the newly created users
                for user in tempCreated:
                    user.delete()

                # Then trigger the validation error (normally raised via
                # serializer.is_valid(raise_exception=True))
                raise serializers.ValidationError(serializer.errors)

            return Response(serializer.data)

    @extend_schema(responses=CourseRosterSerializer)
    @action(detail=True, methods=["PATCH"])
    def addToRoster(self, request, pk=None):
        """
        get:
        Show the roster for a course.

        patch:
        Update the roster for a course.
        """
        user = request.user
        course = self.get_object()

        error = get_roster_permission_errors(user, request, course)
        if error:
            return error

        # Pre-filter fields for any users who do not exist yet
        newStudents: list[User] = []
        newGraders: list[User] = []
        newAdmins: list[User] = []
        newSuperGraders: list[User] = []
        newRubricEditors: list[User] = []
        for keyEl, userList in zip(
            ("students", "graders", "courseAdmins", "superGraders", "rubricEditors"),
            (newStudents, newGraders, newAdmins, newSuperGraders, newRubricEditors),
        ):
            parse_new_users(keyEl, request, userList)
        # Add the users to the course
        course.students.add(*newStudents)
        course.inactive_students.remove(*newStudents)
        course.graders.add(*newGraders)
        course.inactive_graders.remove(*newGraders)
        course.courseAdmins.add(*newAdmins)
        course.inactive_courseAdmins.remove(*newAdmins)
        course.superGraders.add(*newSuperGraders)
        course.rubricEditors.add(*newRubricEditors)
        course.save()

        for admin in newAdmins:
            # Permissions model: once a user is added as a courseadmin to (any) course, they unlock the ability to create courses
            # and modify rosters.
            add_admin_privileges(admin)

            if not admin.is_active or course.emailNewUsers: 
                # Email the admin that they have been added to the course, so they can activate their account, bypasses email new users setting for course
                UserAddedToCourseEmail(admin).send_email(
                    course_name=course.name,
                    course_period=course.period,
                    user_type="admin",
                    force_send=course.emailNewUsers
                )

        # If course setting is set, email newly created users
        if course.emailNewUsers:
            # Email new students

            for userList, roleType in zip(
                (newGraders, newStudents), ("grader", "student")
            ):
                for newUser in userList:
                    UserAddedToCourseEmail(newUser).send_email(
                        course_name=course.name,
                        course_period=course.period,
                        user_type=roleType,
                        force_send=True
                    )

        serializer = CourseRosterSerializer(course, context={"request": request})
        return Response(serializer.data)

    @extend_schema(responses=CourseRosterSerializer)
    @action(detail=True, methods=["PATCH"])
    def removeFromRoster(self, request, pk=None):
        """
        get:
        Show the roster for a course.

        patch:
        Update the roster for a course.
        """
        user = request.user
        course = self.get_object()

        error = get_roster_permission_errors(user, request, course)
        if error:
            return error

        # Pre-filter fields for any users who do not exist yet
        inactiveStudents, inactiveGraders, inactiveAdmins, inactiveSuperGraders, inactiveRubricEditors = (
            [],
            [],
            [],
            [],
            [],
        )
        for keyEl, userList in zip(
            ("students", "graders", "courseAdmins", "superGraders", "rubricEditors"),
            (inactiveStudents, inactiveGraders, inactiveAdmins, inactiveSuperGraders, inactiveRubricEditors),
        ):
            parse_new_users(keyEl, request, userList)
        # Add the users to the course
        course.students.remove(*inactiveStudents)
        course.inactive_students.add(*inactiveStudents)
        course.graders.remove(*inactiveGraders)
        course.inactive_graders.add(*inactiveGraders)
        course.courseAdmins.remove(*inactiveAdmins)
        course.inactive_courseAdmins.add(*inactiveAdmins)
        course.superGraders.remove(*inactiveGraders, *inactiveSuperGraders)
        course.rubricEditors.remove(*inactiveGraders, *inactiveRubricEditors)
        course.save()

        # remove inactive graders and students from their sections
        for section in course.sections.all():
            if len(inactiveGraders) > 0:
                section.leaders.remove(*inactiveGraders)
            if len(inactiveStudents) > 0:
                section.students.remove(*inactiveStudents)
            section.save()

        serializer = CourseRosterSerializer(course, context={"request": request})
        return Response(serializer.data)

    @extend_schema(responses={204: None})
    @action(detail=True, methods=["patch"])
    def deleteRubricCategory(self, request, pk=None):
        user = request.user
        if not isAuthenticated(user):
            return returnNotAuthorized()

        form = IDForm(request.data)
        if form.is_valid():
            course = Course.objects.get(id=pk)

            if not isCourseAdmin(user, course):
                return returnForbidden()

            try:
                category = RubricCategory.objects.get(id=form.cleaned_data["id"])
            except:
                return returnNotFound(message="Category doesn't exist")

            category.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        else:
            return Response(form.errors, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(request=CourseRosterMapSerializer, responses=CourseRosterMapSerializer)
    @action(detail=True, methods=["GET", "PATCH"])
    def rosterMap(self, request, pk=None):
        user = request.user
        if not isAuthenticated(user):
            return returnNotAuthorized()

        course = self.get_object()
        if not isCourseAdmin(user, course):
            return returnForbidden()

        if request.method == "GET":
            serializer = CourseRosterMapSerializer({"rosterMap": course.rosterMap})
            return Response(serializer.data)
        else:
            serializer = CourseRosterMapSerializer(data=request.data)
            if not serializer.is_valid():
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            map = serializer.validated_data.get("rosterMap", {})
            course.rosterMap = map
            course.save()
            return Response(CourseRosterMapSerializer({"rosterMap": course.rosterMap}).data)

    @extend_schema(request=CourseStudentCaptionsSerializer, responses=CourseStudentCaptionsSerializer)
    @action(detail=True, methods=["GET", "PATCH"])
    def studentCaptions(self, request, pk=None):
        user = request.user
        if not isAuthenticated(user):
            return returnNotAuthorized()

        course = self.get_object()
        if not isCourseAdmin(user, course):
            return returnForbidden()

        if request.method == "GET":
            serializer = CourseStudentCaptionsSerializer({"studentCaptions": course.studentCaptions})
            return Response(serializer.data)
        else:
            serializer = CourseStudentCaptionsSerializer(data=request.data)
            if not serializer.is_valid():
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            new_captions = serializer.validated_data.get("studentCaptions", {})
            course.studentCaptions = new_captions
            course.save()
            return Response(CourseStudentCaptionsSerializer({"studentCaptions": course.studentCaptions}).data)

    @extend_schema(responses=SectionSerializer(many=True))
    @action(detail=True, methods=["GET"], pagination_class=LargeObjectsPagination)
    def sections(self, request, pk=None):
        """
        Gets a paginated list of sections for a course.
        We use this for performance for large courses to fetch sections in bulk.
        They're rarely used in admin console operations, so it's a great candidate to paginate
        Returns a list of Section objects
        """
        user = request.user
        course = self.get_object()

        # Only allow course admins to access this endpoint
        if not isCourseAdmin(user, course):
            return returnForbidden()

        sections = course.sections.all().prefetch_related("leaders", "students")
        page = self.paginate_queryset(sections)
        if page is not None:
            serializer = SectionSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = SectionSerializer(sections, many=True)
        return Response(serializer.data)



def add_admin_privileges(user):
    user.profile.canCreateCourses = True
    user.profile.canModifyRosters = True
    user.save()


def get_roster_permission_errors(user, request, course):
    if not isAuthenticated(user):
        return returnNotAuthorized()
    if request.method == "GET":
        if not (
            isCourseAdmin(user, course)
            or isSuperGrader(user, course)
            or user.is_superuser
        ):
            return returnForbidden()
    elif request.method == "PATCH":
        if not (user.is_superuser or (isCourseAdmin(user, course) and user.profile.canModifyRosters)):
            return returnForbidden()
    return False


def parse_new_users(keyEl, request, userList, auto_activate=False):
    if keyEl in request.data:
        # There are two ways to specify a list of values in a request
        # Type 1: request['graders'] = firstEmail, request['graders'] = secondEmail
        # Type 2: request['graders'] = [firstEmail, secondEmail]
        # If Type 1, then .get returns a string (the last value corresponding to the key), and we need to use request.data.getlist
        # If Type 2, then .get returns an array
        # If there are other valid types that we don't currently handle, this view will return a 500 error (thisData won't be defined),
        # which should allow us to figure them out.
        if type(request.data[keyEl]) is str:
            thisData = request.data.getlist(keyEl)
        elif type(request.data[keyEl]) is list:
            thisData = request.data.get(keyEl)

        for email in thisData:
            # Add any newly created users to the creator's
            # organization
            newUser = get_or_create_user(email, request.user.profile.organization, auto_activate=auto_activate)
            userList.append(newUser)
