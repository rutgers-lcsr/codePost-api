from core.models import Course, RubricCategory
from django.contrib.auth.models import User
from core.serializers.course import (
    CourseSerializer,
    CourseRosterSerializer,
    CourseSettingsSerializer,
)
from core.serializers.section import SectionSerializer
from core.serializers.user import UserSerializer
from core.views.template import SuperUserListProtectedViewSet

from rest_framework.response import Response
from rest_framework.decorators import action
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
from core.permissions.helpers import isStudent, isGrader, isCourseAdmin, isCourseMember
from core.permissions.helpers import isStudentOfSub, isStaffOfSub, isSuperGrader

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

        return Response(
            CourseSerializer(
                user.courseAdmin_courses.all(), many=True, context={"request": request}
            ).data
        )

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
            tempCreated = []
            for keyEl in ["students", "graders", "courseAdmins"]:
                parse_new_users(keyEl, request, tempCreated)

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
        newStudents, newGraders, newAdmins, newSuperGraders = [], [], [], []
        for keyEl, userList in zip(
            ("students", "graders", "courseAdmins", "superGraders"),
            (newStudents, newGraders, newAdmins, newSuperGraders),
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
        course.save()

        for admin in newAdmins:
            # Permissions model: once a user is added as a courseadmin to (any) course, they unlock the ability to create courses
            # and modify rosters.
            add_admin_privileges(admin)

        # If course setting is set, email newly created users
        if course.emailNewUsers:
            # Email new students
            for userList, roleType in zip(
                (newAdmins, newGraders, newStudents), ("admin", "grader", "student")
            ):
                for newUser in userList:
                    UserAddedToCourseEmail(newUser).send_email(
                        course_name=course.name,
                        course_period=course.period,
                        user_type=roleType,
                    )
                    # send_new_user_email(newUser, roleType, course)

        serializer = CourseRosterSerializer(course, context={"request": request})
        return Response(serializer.data)

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
        inactiveStudents, inactiveGraders, inactiveAdmins, inactiveSuperGraders = (
            [],
            [],
            [],
            [],
        )
        for keyEl, userList in zip(
            ("students", "graders", "courseAdmins", "superGraders"),
            (inactiveStudents, inactiveGraders, inactiveAdmins, inactiveSuperGraders),
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

    @action(detail=True, methods=["patch"])
    def deleteRubricCategory(self, request, pk=None):
        user = request.user
        if not isAuthenticated(user):
            return returnNotAuthorized()

        form = IDForm(request.POST)
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

    @action(detail=True, methods=["GET", "PATCH"])
    def rosterMap(self, request, pk=None):
        user = request.user
        if not isAuthenticated(user):
            return returnNotAuthorized()

        course = self.get_object()
        if not isCourseAdmin(user, course):
            return returnForbidden()

        if request.method == "GET":
            return Response(course.rosterMap)
        else:
            map = request.data.get("rosterMap", {})
            course.rosterMap = map
            course.save()
            return Response(course.rosterMap)

    @action(detail=True, methods=["GET", "PATCH"])
    def studentCaptions(self, request, pk=None):
        user = request.user
        if not isAuthenticated(user):
            return returnNotAuthorized()

        course = self.get_object()
        if not isCourseAdmin(user, course):
            return returnForbidden()

        if request.method == "GET":
            return Response(course.studentCaptions)
        else:
            new_captions = request.data.get("studentCaptions", {})
            course.studentCaptions = new_captions
            course.save()
            return Response(course.studentCaptions)

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
        if not (isCourseAdmin(user, course) and user.profile.canModifyRosters):
            return returnForbidden()
    return False


def parse_new_users(keyEl, request, userList):
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
            newUser = get_or_create_user(email, request.user.profile.organization)
            userList.append(newUser)
