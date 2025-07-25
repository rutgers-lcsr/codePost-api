import re

from rest_framework import status
from rest_framework.response import Response
from rest_framework.decorators import api_view

from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes

from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator

from core.models import User, Organization, Course
from core.utils import is_course_member, email_passes_whitelist
from core.forms.forms import (
    EmailForm,
    EmailTokenForm,
    ValidateTokenForm,
    CreateAdminForm,
    SetPasswordFromTokenForm,
    OrganizationForm,
    ValidationResponseForm,
    SetCredentialsForm,
)

from core.emails import send_email_sendgrid, get_email_params, get_email_template_id

from core.permissions.helpers import (
    returnNotAuthorized,
    returnForbidden,
    returnNotFound,
)
from core.permissions.helpers import isAuthenticated, can_elevate_permissions

from log.models import Event
import json

from util.slack import Slack

##########################################################################
#####################################     JOIN FLOW     ##################
#####################################                   ##################
##########################################################################


@api_view(["POST"])
def emailRegistration(request):
    """
    Request body includes: email.

    Function to take in email and send activation email in response, if user exists but is inactive
    (which indicates that they have been added to a course by a courseAdmin, but yet to create their
    account.)

    This is intended to allow users who missed their initial activation emails to re-send one
    to themselves.

    """
    form = EmailTokenForm(request.data)
    if form.is_valid():
        try:
            course = Course.objects.get(
                inviteCode=form.cleaned_data["token"], inviteCodeEnabled=True
            )
            try:
                user = User.objects.get(email=form.cleaned_data["email"])
                if email_passes_whitelist(user.email, course.emailWhitelist):
                    course.students.add(user)
                    return Response(
                        {"success": True, "code_valid": True, "email_valid": True},
                        status=status.HTTP_200_OK,
                    )
                else:
                    return Response(
                        {"success": False, "code_valid": True, "email_valid": False},
                        status=status.HTTP_403_FORBIDDEN,
                    )
            except User.DoesNotExist:
                if email_passes_whitelist(
                    form.cleaned_data["email"], course.emailWhitelist
                ):
                    newUser = User.objects.create(
                        username=form.cleaned_data["email"],
                        email=form.cleaned_data["email"],
                        is_active=False,
                    )
                    newUser.profile.organization = course.courseAdmins.all()[
                        0
                    ].profile.organization
                    newUser.save()
                    course.students.add(newUser)
                    send_email_to_joining_user(newUser)
                    return Response(
                        {"success": True, "code_valid": True, "email_valid": True},
                        status=status.HTTP_200_OK,
                    )
                else:
                    return Response(
                        {"success": False, "code_valid": True, "email_valid": False},
                        status=status.HTTP_403_FORBIDDEN,
                    )

        except Course.DoesNotExist:
            # User hasn't been added to any courses, so we deny account creation.
            # Send email.
            # context = {}
            # from_email = 'team@codepost.io'
            # send_email_sendgrid(from_email, form.cleaned_data['email'], get_email_params(
            #     'JOIN_DOESNOTEXIST', context), get_email_template_id('JOIN_DOESNOTEXIST'))
            return Response(
                {"success": False, "code_valid": False, "email_valid": False},
                status=status.HTTP_403_FORBIDDEN,
            )
    else:
        return Response(
            {"success": False, "errors": form.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )


@api_view(["POST"])
def verifyRegistrationToken(request):
    """
    Handle valid verify email links sent after account creation.

    Function takes a (uid, token) as input and determines if the pair is valid.

    This is used to inform the client whether a user presenting (uid, token) should be shown a form
    to set their password.

    """
    form = ValidateTokenForm(request.data)
    if form.is_valid():
        uid_int = urlsafe_base64_decode(form.cleaned_data["uid"]).decode()
        try:
            user = User.objects.get(id=uid_int)
            isValid = default_token_generator.check_token(
                user, form.cleaned_data["token"]
            )
            return Response(
                {"isValid": isValid, "email": user.email}, status=status.HTTP_200_OK
            )
        except User.DoesNotExist:
            return Response({"isValid": False}, status=status.HTTP_200_OK)
    else:
        return Response(
            {"isValid": False, "errors": form.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )


@api_view(["POST"])
def registerAndSetPassword(request):
    """
    Function takes a (uid, token) as authorization and, if authorization is valid, sets the associated
    user's password to the password payload.

    This is used in response to account activation emails (both generated via the "join" signup flow
    and automatically generated by roster additions)

    """
    form = SetPasswordFromTokenForm(request.data)
    if form.is_valid():
        uid_int = urlsafe_base64_decode(form.cleaned_data["uid"]).decode()
        try:
            user = User.objects.get(id=uid_int)
            isValid = default_token_generator.check_token(
                user, form.cleaned_data["token"]
            )
            if isValid:
                user.is_active = True
                user.set_password(form.cleaned_data["password1"])
                user.save()
                return Response({"isValid": True}, status=status.HTTP_200_OK)
            else:
                return Response(
                    {"isValid": False, "errors": {"token": "invalid token"}},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        except User.DoesNotExist:
            return Response(
                {"isValid": False, "errors": {"token": "invalid token"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
    else:
        return Response(
            {"isValid": False, "errors": form.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )


## CIP specific ##
@api_view(["POST"])
def setCredentials(request):
    """
    If a user is logged in by hasn't yet set a usable password, they can use this endpoint to do so, as well
    as specify their organization.

    """
    user = request.user
    if not isAuthenticated(user):
        return returnNotAuthorized()

    # only want this to work if a user doesn't already have a usable password
    if user.password and user.has_usable_password():
        return Response(
            "You don't have permission to perform this action. Password already set.",
            status.HTTP_403_FORBIDDEN,
        )

    form = SetCredentialsForm(request.data)
    if form.is_valid():
        org_name = form.cleaned_data["organization"]
        try:
            org = Organization.objects.get(shortname=org_name)
        except Organization.DoesNotExist:
            org = Organization.objects.create(name=org_name, shortname=org_name)

        user.is_active = True
        user.set_password(form.cleaned_data["password1"])
        user.profile.organization = org
        user.save()

        return Response({"isValid": True}, status=status.HTTP_200_OK)
    else:
        return Response(
            {"isValid": False, "errors": form.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )


## CIP specific ##
@api_view(["POST"])
def graderToAdmin(request):
    """
    Allows a user who is only a grader to elevate their status to level of admin within their organization.
    The role elevation allows the admin to create new courses, but not join existing courses.
    """

    user = request.user
    if not isAuthenticated(user):
        return returnNotAuthorized()

    if can_elevate_permissions(user):
        user.profile.canModifyRosters = True
        user.profile.canCreateCourses = True
        user.save()
        return Response({}, status=status.HTTP_200_OK)
    else:
        return Response({}, status=status.HTTP_400_BAD_REQUEST)


def send_email_to_joining_user(user):
    raise NotImplementedError(
        "This function is deprecated. Use AddedUserToOrganizationEmail instead."
    )
    """
    Send a signup email to a user who has been added to at least 1 course.
    """
    from_email = "team@codepost.io"
    if user.is_active:
        # User already has a password set. Send notification email
        context = {}
        send_email_sendgrid(
            from_email,
            user.email,
            get_email_params("JOIN_ACTIVE", context),
            get_email_template_id("JOIN_ACTIVE"),
        )
    else:
        # Proceed with account verification
        context = {
            "uid": urlsafe_base64_encode(force_bytes(user.pk)),
            "token": default_token_generator.make_token(user),
        }
        send_email_sendgrid(
            from_email,
            user.email,
            get_email_params("JOIN_INACTIVE", context),
            get_email_template_id("JOIN_INACTIVE"),
        )


def send_email_to_joining_user_mooc(user):
    raise NotImplementedError(
        "This function is deprecated. not longer using mooc"
    )

    """
    Send a signup email to a user who has been added to at least 1 course.
    """
    from_email = "mooc@codepost.io"
    # Proceed with account verification
    context = {
        "uid": urlsafe_base64_encode(force_bytes(user.pk)),
        "token": default_token_generator.make_token(user),
    }
    send_email_sendgrid(
        from_email,
        user.email,
        get_email_params("JOIN_INACTIVE_MOOC", context),
        get_email_template_id("JOIN_INACTIVE"),
    )


##########################################################################
#####################################    CREATE FLOW    ##################
#####################################                   ##################
##########################################################################


def sendSlackMessage(message, attachments=[]):
    raise NotImplementedError(
        "This function is deprecated. using Logger instead."
    )
    
    # sc = Slack()
    # sc.send_message(message, attachments=attachments, channel="#user_signups")


@api_view(["POST"])
def validateMoocSignup(request):
    raise NotImplementedError(
        "This function is deprecated. not longer using mooc"
    )

    """
    Most FaaS users will be signed up through the Order flow (serializers.Order)
    rather than this endpoint
    """
    form = EmailForm(request.data)  # email

    if form.is_valid():
        (user, is_new) = User.objects.get_or_create(
            email=form.cleaned_data["email"], username=form.cleaned_data["email"]
        )

        if not is_new:
            return Response({"success": False}, status=status.HTTP_200_OK)
        else:
            user.is_active = False
            organization = Organization.objects.get(name="mooc")
            user.profile.organization = organization
            user.save()

            # Send join email
            send_email_to_joining_user_mooc(user)

            return Response({"success": True}, status=status.HTTP_200_OK)

    else:
        sendSlackMessage(
            ":warning: *A new MOOC user experienced an unknown error when signing up.* Form: {}".format(
                form
            )
        )
        return Response(
            {
                "success": False,
                "action_id": ".".join(map(str, action_id)),
                "errors": form.errors,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )


@api_view(["POST"])
@permission_classes([AllowAny])
def validateNewAdminUser(request):
    """
    Function is used to trigger manual account validation in response to a user requesting their account
    be granted course creation privileges.

    Currently Vurnable to abuse, any user can call this endpoint and create an admin account. 
    """
    action_id = []

    form = CreateAdminForm(request.data)  # organization, email
    if form.is_valid():
        rawName = form.cleaned_data["organization"]
        shortnameFromForm = rawName.replace(" ", "").lower()[0 : min(12, len(rawName))]

        # Case 1: user exists
        try:
            user = User.objects.get(email=form.cleaned_data["email"])
            org = user.profile.organization
            action_id.append(1)
            is_student_or_grader = (user.student_courses.count() > 0) or (
                user.grader_courses.count() > 0
            )
            # If they do, check to see if their saved organization matches the
            # organization they are trying to sign up to
            if not (
                user.profile.organization
                and user.profile.organization.shortname.lower() == shortnameFromForm
            ):
                action_id.append(1)

                if is_student_or_grader and (not user.profile.canModifyRosters):
                    send_email_to_joining_user(user)
                else:
                    # Send user an email asking them to confirm they want to change their
                    # organization by emailing team@codepost.io
                    from_email = "team@codepost.io"
                    context = {}
                    send_email_sendgrid(
                        from_email,
                        user.email,
                        get_email_params("CREATE_ORGANIZATION_CHANGE", context),
                        get_email_template_id("CREATE_ORGANIZATION_CHANGE"),
                    )

                    # Alert codePost team via Slack
                    sendSlackMessage(
                        ":warning: *{} tried to change organizations when signing up as an admin.* \nUser Org `{}` != Form Org `{}`".format(
                            user.email,
                            user.profile.organization.shortname,
                            shortnameFromForm,
                        )
                    )

                return Response(
                    {"success": True, "action_id": ".".join(map(str, action_id))},
                    status=status.HTTP_200_OK,
                )
            else:
                action_id.append(2)

        # Case 2: user does not exist, so create them
        except User.DoesNotExist:
            action_id.append(2)
            # If they don't, create them
            user = User.objects.create(
                username=form.cleaned_data["email"], email=form.cleaned_data["email"]
            )
            user.is_active = False
            is_student_or_grader = (user.student_courses.count() > 0) or (
                user.grader_courses.count() > 0
            )

            # Case 2a: the organization the user is trying to join already exists.
            try:
                org = Organization.objects.get(shortname=shortnameFromForm)
                user.profile.organization = org
                user.save()
                action_id.append(1)

            # Case 2b: the organization the user is trying to join does not exist, so
            # create it
            except Organization.DoesNotExist:
                org = Organization.objects.create(
                    name=shortnameFromForm, shortname=shortnameFromForm
                )
                user.profile.organization = org
                user.save()
                action_id.append(2)

        # From now on, we can assume user exist and organization matches specified
        # org

        if user.is_active and user.profile.canModifyRosters:
            action_id.append(1)
            # If user already exists and has been validated, then email them
            # from_email = "team@codepost.io"
            # context = {}
            # send_email_sendgrid(
            #     from_email,
            #     user.email,
            #     get_email_params("CREATE_ALREADY_ADMIN", context),
            #     get_email_template_id("CREATE_ALREADY_ADMIN"),
            # )
            # sendSlackMessage(
            #     ":warning: *{} tried to sign up as an admin, but they already are an admin.*".format(
            #         user.email
            #     )
            # )

            # Return success response, indicating that the user is already an admin

            return Response(
                {"success": True, "action_id": ".".join(map(str, action_id))},
                status=status.HTTP_200_OK,
            )
        else:
            action_id.append(2)
            # Figure out if we can automatically approve this user
            # email_ends_with_edu = user.email[-4:] == ".edu"
            NewAdminRequestEmail(
                user, org.name
            ).send_email()

            # ## FLAG: all users are now automatically approved
            # if not is_student_or_grader:
            #     action_id.append(1)
            #     # auto-approve
            #     approve_new_admin_user(user, auto_approved=True, org_name=org.name)

            # else:
            #     action_id.append(2)
            #     # require codePost team approval
              
            #     # if is_student_or_grader:
            #     #     # send this user through the join flow
            #     #     sendSlackMessage(
            #     #         "{} tried to sign up as a new admin from {}. He/she was a course member, so I sent them the join email.".format(
            #     #             user.email, org.name
            #     #         )
            #     #     )
            #     #     # change this to the right role
            #     #     AddedUserToOrganizationEmail(
            #     #         user, org.name, "admin"
            #     #     ).send_email()
            #     #     # send_email_to_joining_user(user)

            #     # else:
            #     #     # email codePost admins
            #     #     user.profile.pendingValidation = True
            #     #     user.profile.canModifyRosters = True
            #     #     user.save()
            #     #     from_email = "team@codepost.io"
            #     #     to_email = "team@codepost.io"
            #     #     context = {
            #     #         "user": user.email,
            #     #         "uid": urlsafe_base64_encode(force_bytes(user.pk)),
            #     #         "token": default_token_generator.make_token(user),
            #     #         "organization": shortnameFromForm,
            #     #     }

            #     #     email_params = get_email_params("CREATE_VALIDATION", context)
            #     #     send_email_sendgrid(
            #     #         from_email,
            #     #         to_email,
            #     #         email_params,
            #     #         get_email_template_id("CREATE_VALIDATION"),
            #     #     )
            #     #     attachments = [
            #     #         {
            #     #             "text": "What should we do?",
            #     #             "fallback": "What should we do?",
            #     #             "color": "#24BE85",
            #     #             "attachment_type": "default",
            #     #             "actions": [
            #     #                 {
            #     #                     "name": "approval",
            #     #                     "text": "Approve",
            #     #                     "type": "button",
            #     #                     "value": "approve",
            #     #                     "confirm": {
            #     #                         "title": "Are you sure?",
            #     #                         "ok_text": "Yes",
            #     #                         "dismiss_text": "No",
            #     #                     },
            #     #                     "url": email_params["url"] + "&activate=true",
            #     #                 },
            #     #                 {
            #     #                     "name": "approval",
            #     #                     "text": "Deny",
            #     #                     "type": "button",
            #     #                     "value": "deny",
            #     #                     "confirm": {
            #     #                         "title": "Are you sure?",
            #     #                         "ok_text": "Yes",
            #     #                         "dismiss_text": "No",
            #     #                     },
            #     #                     "url": email_params["url"],
            #     #                 },
            #     #             ],
            #     #         }
            #     #     ]

            #     #     sendSlackMessage(
            #     #         ":white_check_mark: *{} just signed up as an admin from {}*".format(
            #     #             user.email, shortnameFromForm
            #     #         ),
            #     #         attachments,
            #     #     )

            return Response(
                {"success": True, "action_id": ".".join(map(str, action_id))},
                status=status.HTTP_200_OK,
            )
    else:
        sendSlackMessage(
            ":warning: *A new user experienced an unknown error when signing up.* Form: {}".format(
                form
            )
        )
        return Response(
            {
                "success": False,
                "action_id": ".".join(map(str, action_id)),
                "errors": form.errors,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )


@api_view(["GET"])
def handleValidationResponse(request):
    """
    Function is used to respond to validation instructions from codePost admins (sent via URL).

    In response to a valid activation grant, set user.canModifyRosters = True and user.pendingValidation = False.

    In response to a valid activation deny, set user.pendingValidation = False and if user is not a member of
    any courses, delete that user.

    """
    form = ValidationResponseForm(request.query_params)
    if form.is_valid():
        uid_int = urlsafe_base64_decode(form.cleaned_data["uid"]).decode()
        try:
            user = User.objects.get(id=uid_int)
            isValid = default_token_generator.check_token(
                user, form.cleaned_data["token"]
            )
            if user.profile.pendingValidation:
                if isValid:
                    if form.cleaned_data["activate"]:
                        # granting privilege

                        approve_new_admin_user(user)

                    else:
                        # denying privilege
                        Event.objects.create(
                            category="registration",
                            user=str(user),
                            description="New admin denied",
                        )
                        sendSlackMessage(
                            ":warning: *A codePost team member denied new admin {}.*".format(
                                user.email
                            )
                        )

                        # to the privilege request. Since we are denying that request,
                        # delete them.
                        if not is_course_member(user):
                            user.delete()

                return Response({"isValid": isValid}, status=status.HTTP_200_OK)
            else:
                return Response(
                    {
                        "isValid": False,
                        "message": "This user is not pending validation.",
                    },
                    status=status.HTTP_200_OK,
                )
        except User.DoesNotExist:
            return Response({"isValid": False}, status=status.HTTP_200_OK)
    else:
        return Response({"errors": form.errors}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET"])
def checkStatusNewAdminUser(request):
    """
    Allows the client to check on the status of a validation request for a given user.

    This view is invoked by the UI to monitor progress of validation requests.

    """
    email = request.query_params.get("email", None)
    form = EmailForm({"email": email})
    if form.is_valid():
        try:
            user = User.objects.get(email=email)
            isPending = user.profile.pendingValidation

            # we don't want to show that verification has failed if we passed the user through to the
            # join flow
            is_student_or_grader = (user.student_courses.count() > 0) or (
                user.grader_courses.count() > 0
            )

            isActivated = (
                False
                if isPending
                else (user.profile.canModifyRosters or is_student_or_grader)
            )
            return Response(
                {"pending": isPending, "status": isActivated}, status=status.HTTP_200_OK
            )
        except:
            return Response(
                {"pending": False, "status": False}, status=status.HTTP_200_OK
            )
    else:
        return Response({"errors": form.errors}, status=status.HTTP_400_BAD_REQUEST)


def approve_new_admin_user(user, auto_approved=False, org_name=""):
    """
    Approve the creation of a new user who has the ability to create new courses.
    """
    user.profile.canModifyRosters = True
    user.profile.canCreateCourses = True
    user.profile.pendingValidation = False
    user.save()

    # send registration email
    from_email = "team@codepost.io"
    context = {
        "uid": urlsafe_base64_encode(force_bytes(user.pk)),
        "token": default_token_generator.make_token(user),
    }
    NewAdminEmail(user, user.profile.organization, 'admin').send_email()

    
    # send_email_sendgrid(
    #     from_email,
    #     user.email,
    #     get_email_params("CREATE_SUCCESS", context),
    #     get_email_template_id("CREATE_SUCCESS"),
    # )

    # notify codePost team via Slack
    slack_message = (
        ":white_check_mark: *A codePost team member approved new admin {} from {}.*"
    )
    if auto_approved:
        slack_message = (
            ":white_check_mark: *codePost automatically approved new admin {} from {}.*"
        )

    meta = {auto_approved: auto_approved}

    Event.objects.create(
        category="registration",
        user=str(user),
        description="New admin signup",
        meta=json.dumps(meta),
    )
    sendSlackMessage(slack_message.format(user.email, org_name))


##########################################################################
##################################### PW RESET FUNCTIONS #################
#####################################                   ##################
##########################################################################


@api_view(["POST"])
def emailPasswordReset(request):
    is_mooc = request.data.get("is_mooc", False)

    form = EmailForm(request.data)
    if form.is_valid():
        try:
            user = User.objects.get(email=form.cleaned_data["email"])
            if user.is_active:
                # User exists
                from_email = "team@codepost.io"
                context = {
                    "uid": urlsafe_base64_encode(force_bytes(user.pk)),
                    "token": default_token_generator.make_token(user),
                }

                email_template = (
                    "PASSWORD_RESET" if not is_mooc else "PASSWORD_RESET_MOOC"
                )
                send_email_sendgrid(
                    from_email,
                    user.email,
                    get_email_params(email_template, context),
                    get_email_template_id("PASSWORD_RESET"),
                )
            else:
                # User exists, but has never set their password
                from_email = "team@codepost.io"
                context = {
                    "uid": urlsafe_base64_encode(force_bytes(user.pk)),
                    "token": default_token_generator.make_token(user),
                }
                email_template = (
                    "JOIN_INACTIVE" if not is_mooc else "JOIN_INACTIVE_MOOC"
                )
                send_email_sendgrid(
                    from_email,
                    user.email,
                    get_email_params(email_template, context),
                    get_email_template_id("JOIN_INACTIVE"),
                )
        except User.DoesNotExist:
            pass

        return Response({"success": True}, status=status.HTTP_200_OK)
    else:
        return Response(
            {"success": False, "errors": form.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )


@api_view(["POST"])
def verifyResetToken(request):
    """
    Handle valid verify email links sent after password reset requests.
    """
    form = ValidateTokenForm(request.data)
    if form.is_valid():
        uid_int = urlsafe_base64_decode(form.cleaned_data["uid"]).decode()
        try:
            user = User.objects.get(id=uid_int)
            isValid = default_token_generator.check_token(
                user, form.cleaned_data["token"]
            )
            return Response(
                {"isValid": isValid, "email": user.email}, status=status.HTTP_200_OK
            )
        except User.ObjectDoesNotExist:
            return Response({"isValid": False}, status=status.HTTP_200_OK)
    else:
        return Response({"isValid": False}, status=status.HTTP_200_OK)


@api_view(["POST"])
def resetPassword(request):
    # Probably should enforce some password checks here...currently, users
    # can bypass any client-side password requirements using this endpoint
    form = ChangePasswordForm(request.POST)
    if form.is_valid():
        uid_int = urlsafe_base64_decode(form.cleaned_data["uid"]).decode()
        try:
            user = User.objects.get(id=uid_int)
            isValid = default_token_generator.check_token(
                user, form.cleaned_data["token"]
            )
            if isValid:
                # Update password
                user.set_password(form.cleaned_data["password"])
                user.save()
            return Response(
                {"isValid": isValid, "success": True}, status=status.HTTP_200_OK
            )
        except User.DoesNotExist:
            return Response(
                {"isValid": False, "success": False}, status=status.HTTP_200_OK
            )
    else:
        return Response({"isValid": False, "succes": False}, status=status.HTTP_200_OK)
