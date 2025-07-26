from abc import ABC, abstractmethod
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
import pytz
from codepost.settings import (
    CLIENT_URL,
    MOOC_CLIENT_URL,
    API_URL,
    DEFAULT_EMAIL_FROM,
    OVERRIDE_EMAIL,
    ADMINS
)

from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.contrib.auth.models import User
from django import forms

import logging
from core.handlers.submission_version_handler import SubmissionVersionHandler
from core.handlers.submission_version_handler import SubmissionVersionHandler
from core.logging import log_debug, logEvent
from core.models import Assignment, Submission

from core.tests.views.results import submission

class CodepostEmail(ABC):
    subject = "CodePost Notification"
    template = "emails/base_template.html"

    def __init__(self, user:User):
        self.user = user
        self.from_email = DEFAULT_EMAIL_FROM

    def _get_base_context(self):
        """
        Returns the base context for the email.
        This can be overridden by subclasses to add more context.
        """
        return {
            "user": self.user,
            "from_email": self.get_from_address(),
            "to_email": self.get_to_address(),
            "client_url": CLIENT_URL,
        }
    def get_context(self, **kwargs):
        """
        Returns the context for the email.
        This method allows context to be extended by subclasses.
        """
        context = self._get_base_context()
        context.update(kwargs)
        return context
    
    @abstractmethod
    def send_email(self):
        """
        This method should be implemented by subclasses to send the email.
        It should return the response from the email service or None if in testing mode.
        Should call send() to send the email.
        """
        pass
    
    def get_to_address(self):
        if OVERRIDE_EMAIL:
            return OVERRIDE_EMAIL

        if self.user.email:
            return self.user.email

        if self.user.organization and self.user.organization.email:
            return self.user.organization.email

        raise ValueError("User does not have an email address set.")
    
    def get_from_address(self):
        """
        Returns the email address from which the email should be sent.
        If SENDGRID_OVERRIDE_EMAIL is set, it returns that email address.
        Otherwise, it returns the default from email.
        """
        return self.from_email

    def get_admin_emails(self):
        """
        Returns a list of admin emails for the organization.
        If the user is not part of an organization, it returns an empty list.
        """
        return ADMINS

    def send(self, email:EmailMessage, type:str = "html"):
        """
        Sends the email using the Django EmailMessage class.
        """
        
        try:
            email.content_subtype = type 
            logEvent(event="Email sent", message="{} sent to {}".format(self.subject, self.get_to_address()))


            email.send()
        except Exception as e:
            # Will log out the error in the Django logs
            logEvent(event="Email send failed", message=str(e), level=logging.ERROR)
            return None


class UserAddedToCourseEmail(CodepostEmail):
    subject = "You have been added to a course on CodePost"
    template = "emails/user/add_to_course_template.html"

    def send_email(self, course_name:str, course_period:str, user_type:str):
        """
        Sends an email to the user notifying them that they have been added to a course.
        """
        if self.user.is_active:
            context = self.get_context(
                role=user_type,
                course_name=course_name,
                course_period=course_period,
            )
        else:
            context = self.get_context(
                role=user_type,
                course_name=course_name,
                course_period=course_period,
                uid=urlsafe_base64_encode(force_bytes(self.user.pk)),
                token=default_token_generator.make_token(self.user),
            )

        html_content = render_to_string(self.template, context)

        email = EmailMessage(
            subject=self.subject,
            body=html_content,
            from_email=self.get_from_address(),
            to=[self.get_to_address()],
        )
        return self.send(email)
class UserSignupEmail(CodepostEmail):
    subject = "Welcome to CodePost"
    template = "emails/user/signup_template.html"

    def send_email(self):
        """
        Sends a welcome email to the user after they sign up.
        """
        if self.user.is_active:
            context = self.get_context()
        else:
            context = self.get_context(
                uid=urlsafe_base64_encode(force_bytes(self.user.pk)),
                token=default_token_generator.make_token(self.user),
            )

        html_content = render_to_string(self.template, context)

        email = EmailMessage(
            subject=self.subject,
            body=html_content,
            from_email=self.get_from_address(),
            to=[self.get_to_address()],
        )
        return self.send(email)

class AdminAlreadyEmail(CodepostEmail):
    subject = "You are already an admin on CodePost"
    template = "emails/admin/already_template.html"

    def send_email(self):
        """
        Sends an email to the user notifying them that they are already an admin.
        """
        context = self.get_context()

        html_content = render_to_string(self.template, context)

        email = EmailMessage(
            subject=self.subject,
            body=html_content,
            from_email=self.get_from_address(),
            to=[self.get_to_address()],
        )
        return self.send(email)

class AdminChangeOrganizationEmail(CodepostEmail):
    subject = "Your organization has changed on CodePost"
    template = "emails/admin/change_organization_template.html"

    def send_email(self, organization_name:str):
        """
        Sends an email to the user notifying them that their organization has changed.
        """
        context = self.get_context(
            uid=urlsafe_base64_encode(force_bytes(self.user.pk)),
            token=default_token_generator.make_token(self.user),
            organization=organization_name
        )

        html_content = render_to_string(self.template, context)

        email = EmailMessage(
            subject=self.subject,
            body=html_content,
            from_email=self.get_from_address(),
            to=[self.get_to_address()],
        )
        return self.send(email)


class PasswordResetEmail(CodepostEmail):
    subject = "Password Reset Request"
    template = "emails/user/password_reset_template.html"

    def send_email(self):
        """
        Sends a password reset email to the user.
        """
        context = self.get_context(
            uid=urlsafe_base64_encode(force_bytes(self.user.pk)),
            token=default_token_generator.make_token(self.user),
        )

        html_content = render_to_string(self.template, context)

        email = EmailMessage(
            subject=self.subject,
            body=html_content,
            from_email=self.get_from_address(),
            to=[self.get_to_address()],
        )
        return self.send(email)

class NewAdminRequestEmail(CodepostEmail):
    subject = "New Admin Request on CodePost"
    template = "emails/admin/request_template.html"

    def send_email(self, organization_name:str):
        """
        Sends an email to the CodePost team notifying them of a new admin request.
        """
        context = self.get_context(
            organization=organization_name,
            uid=urlsafe_base64_encode(force_bytes(self.user.pk)),
            token=default_token_generator.make_token(self.user),
        )

        html_content = render_to_string(self.template, context)

        email = EmailMessage(
            subject=self.subject,
            body=html_content,
            from_email=self.get_from_address(),
            to=[self.get_admin_emails()],
        )

        return self.send(email)
class NewAdminActivationEmail(CodepostEmail):
    subject = "New Admin Activation on CodePost"
    template = "emails/admin/activation_template.html"

    def send_email(self, organization_name:str):
        """
        Sends an email to the user notifying them that they have been activated as an admin.
        """
        context = self.get_context(
            organization=organization_name,
            uid=urlsafe_base64_encode(force_bytes(self.user.pk)),
            token=default_token_generator.make_token(self.user),
        )

        html_content = render_to_string(self.template, context)

        email = EmailMessage(
            subject=self.subject,
            body=html_content,
            from_email=self.get_from_address(),
            to=[self.get_to_address()],
        )
        return self.send(email)

class TestRunAllCompleteEmail(CodepostEmail):
    subject = "Test Run All Complete on CodePost"
    template = "emails/admin/test_complete_template.html"

    def send_email(self, assignment_name:str, course_name:str, course_period:str):
        """
        Sends an email to the user notifying them that the test run is complete.
        """

        context = self.get_context(
            assignment_name=assignment_name,
            course_name=course_name,
            course_period=course_period,
        )
        html_content = render_to_string(self.template, context)

        email = EmailMessage(
            subject=self.subject,
            body=html_content,
            from_email=self.get_from_address(),
            to=[self.get_to_address()],
        )
        return self.send(email)

class StudentUploadReceiptEmail(CodepostEmail):
    subject = "Student Upload Receipt on CodePost"
    template = "emails/student/upload_receipt_template.html"

    def send_email(self, submission:Submission):
        """
        Sends an email to the user notifying them of a student upload receipt.
        """
        tz = pytz.timezone(submission.assignment.course.timezone)
        dateUploaded = submission.dateUploaded.astimezone(tz)

        dateUploadedHumanize = dateUploaded.strftime("%A, %m-%d-%Y %H:%M:%S")
        dateUploadedTimestamp = dateUploaded.strftime("%Y%m%d_%H%M")
        
        files = SubmissionVersionHandler(submission).encoded_zip()
        zip_name = "{}_{}_{}.zip".format(self.get_to_address(), submission.id, dateUploaded.strftime("%Y-%m-%d_%H-%M-%S"))
        
        attachments = [
            {
                "content": files,
                "filename": zip_name,
                "type": "application/zip"
            }
        ]
        context = self.get_context(
            assignment_name=submission.assignment.name,
            course_name=submission.assignment.course.name,
            students=", ".join(list(submission.students.all().values_list('email', flat=True))),
            date_uploaded_humanize=dateUploadedHumanize,
            date_uploaded_timestamp=dateUploadedTimestamp,
        )

        html_content = render_to_string(self.template, context)

        email = EmailMessage(
            subject=self.subject,
            body=html_content,
            from_email=self.get_from_address(),
            to=[self.get_to_address()],
            attachments=attachments,
        )
        return self.send(email)

class StudentPartnersAddedEmail(CodepostEmail):
    subject = "Partners Added on CodePost"
    template = "emails/student/partners_added_template.html"

    def send_email(self,submission:Submission, new_partner_email:str):
        """
        Sends an email to the user notifying them that partners have been added.
        """

        partner_emails = ", ".join(list(submission.partners.all().values_list('email', flat=True)))

        context = self.get_context(
            new_partner_email=new_partner_email,
            assignment_name=submission.assignment.name,
            course_name=submission.assignment.course.name,
            course_period=submission.assignment.course.period,
            partners= partner_emails,
        )

        html_content = render_to_string(self.template, context)

        email = EmailMessage(
            subject=self.subject,
            body=html_content,
            from_email=self.get_from_address(),
            to=[self.get_to_address()],
        )
        return self.send(email)

class StudentFeedbackNotificationEmail(CodepostEmail):
    subject = "Feedback Notification on CodePost"
    template = "emails/student/feedback_notification_template.html"

    def send_email(self, submission:Submission):
        """
        Sends an email to the user notifying them of feedback on their submission.
        """
        context = self.get_context(
            submission=submission,
        )

        html_content = render_to_string(self.template, context)

        email = EmailMessage(
            subject=self.subject,
            body=html_content,
            from_email=self.get_from_address(),
            to=[self.get_to_address()],
        )
        return self.send(email)

def send_email_sendgrid(from_email, to_email, params, templateID, attachments=None):
    raise NotImplementedError("This function is deprecated. Use CodepostEmail subclasses instead.")



def get_email_params(identifier, context):
    raise NotImplementedError("This function is deprecated. Use CodepostEmail subclasses instead.")
    if identifier == "ADD_NEW ✅": 
        return add_new_user_template(context)
    elif identifier == "ADD_EXISTING ✅":
        return add_existing_user_template(context)
    # elif identifier == "UPGRADE_ACTIVE":
    #     return upgrade_active_user_template(context)
    # elif identifier == "UPGRADE_INACTIVE":
    #     return upgrade_inactive_user_template(context)
    # elif identifier == "UPGRADE_DOESNOTEXIST":
        # return upgrade_non_user(context)
    elif identifier == "JOIN_ACTIVE ✅":
        return join_active_user_template(context)
    elif identifier == "JOIN_INACTIVE ✅":
        return join_inactive_user_template(context)
    elif identifier == "JOIN_INACTIVE_MOOC ✅":
        return join_inactive_user_mooc_template(context)
    elif identifier == "JOIN_DOESNOTEXIST ✅":
        return join_non_user(context)
    elif identifier == "CREATE_ALREADY_ADMIN ✅":
        return create_already_admin(context)
    elif identifier == "CREATE_ORGANIZATION_CHANGE ✅":
        return create_organization_change(context)
    elif identifier == "CREATE_VALIDATION ✅":
        return validation_check_to_codepost_team(context)
    elif identifier == "CREATE_SUCCESS  ✅":
        return create_admin_success(context)
    # elif identifier == "CREATE_WELCOME ":
    #     return create_admin_welcome(context)
    elif identifier == "PASSWORD_RESET   ✅":
        return password_reset(context)
    # elif identifier == "PASSWORD_RESET_MOOC":
    #     return password_reset_mooc(context)
    elif identifier == "PUBLISH_ASSIGNMENT":
        return publish_assignment(context)
    elif identifier == "GRADER_REMINDER":
        return grader_reminder(context)
    elif identifier == "REGRADES_REMINDER":
        return grader_reminder(context)
    elif identifier == "PARTNERS_ADDED":
        return partners_added(context)
    elif identifier == "STUDENT_UPLOAD_RECEIPT":
        return student_upload_receipt(context)
    elif identifier == "STUDENT_FEEDBACK_NOTIFICATION":
        return student_feedback_notification(context)
    elif identifier == "MOOC_FOLLOW_UP":
        return mooc_follow_up(context)
    elif identifier == "RUN_ALL_COMPLETE":
        return context
    else:
        return None


SENDGRID_TEMPLATE_MAP = {
    "ADD_NEW": "d-97431d25d4de4438872f79670a99de31",
    "ADD_EXISTING": "d-337d703fade64e5ebfc6dce89e923061",
    "UPGRADE_ACTIVE": "d-df87682f990b4d43b6c5c78b80ba404f",
    "UPGRADE_INACTIVE": "d-d2d77fafa7de45aeac0d8d4e8ef86fa7",
    "UPGRADE_DOESNOTEXIST": "d-31a9650711b8413c9987db63a18df01d",
    "JOIN_ACTIVE": "d-628cbde6ba174cf8aafe76511476a3d7",
    "JOIN_INACTIVE": "d-9757d778949246a9a78b7d0019299e1a",
    "JOIN_DOESNOTEXIST": "d-fe07cdd517e74ee6984410b1e58c8cee",
    "CREATE_ALREADY_ADMIN": "d-09a73dd1c7d641c28ba4496f3e3ff8bb",
    "CREATE_ORGANIZATION_CHANGE": "d-36db0423b06c4a17a953d4e3f31fcf30",
    "CREATE_VALIDATION": "d-2edc83acc1954864aba8fe489d366673",
    "CREATE_SUCCESS": "d-d868bb0c71274cd5a13218beee870f13",
    "CREATE_WELCOME": "d-cc02cfa22e6b40fab10da4257214dbea",
    "PASSWORD_RESET": "d-96473559abf24282b7570db7bb9b2438",
    "PUBLISH_ASSIGNMENT": "d-1519960edc65481cbdf483558a51901b",
    "GRADER_REMINDER": "d-c388c8ab420a46a7b66d1d37af6063bd",
    "REGRADES_REMINDER": "d-848500476044437080576292966440a8",
    "RUN_ALL_COMPLETE": "d-33a54cf9d77d41f7afb0165e38f920b7",
    "PARTNERS_ADDED": "d-e178c2204159473cabae2a7488e7a650",
    "STUDENT_UPLOAD_RECEIPT": "d-f574b00b9f8c46f282630d9a5ee0f543",
    "STUDENT_FEEDBACK_NOTIFICATION": "d-eccbca5804a54e43af9b8c8a60210cf7",
    "MOOC_FOLLOW_UP": "d-04335584eb1a4655827b3f18fc8b4dd4",
}

# SendGrid Template ID


def get_email_template_id(identifier):
    raise NotImplementedError("This function is deprecated. Use CodepostEmail subclasses instead.")
    return SENDGRID_TEMPLATE_MAP.get(identifier, None)


#######################################################################################################
#####################################      ROSTER       ###############################################
#####################################                   ###############################################
#######################################################################################################


def add_existing_user_template(context):
    raise NotImplementedError(
        "This function is deprecated. Use Email Classes instead."
    )


def add_new_user_template(context):
    raise NotImplementedError(
        "This function is deprecated. Use Email Classes instead."
    )
   


#######################################################################################################
#####################################    UPGRADE FLOW   ###############################################
#####################################                   ###############################################
#######################################################################################################


def upgrade_active_user_template(context):
    params = {"url": CLIENT_URL}
    return params


def upgrade_inactive_user_template(context):
    params = {"url": CLIENT_URL, "uid": context["uid"], "token": context["token"]}
    return params


def upgrade_non_user(context):
    params = {"url": CLIENT_URL}
    return params


#######################################################################################################
#####################################     JOIN FLOW     ###############################################
#####################################                   ###############################################
#######################################################################################################


def join_active_user_template(context):
    params = {"url": CLIENT_URL}
    return params


def join_inactive_user_template(context):
    params = {"url": CLIENT_URL, "uid": context["uid"], "token": context["token"]}
    return params


def join_inactive_user_mooc_template(context):
    params = {"url": MOOC_CLIENT_URL, "uid": context["uid"], "token": context["token"]}
    return params


def join_non_user(context):
    params = {"url": CLIENT_URL}
    return params


#######################################################################################################
#####################################    CREATE FLOW    ###############################################
#####################################                   ###############################################
#######################################################################################################


def create_organization_change(context):
    return {}


def create_already_admin(context):
    return {}


def validation_check_to_codepost_team(context):
    urlString = "%s/registration/handleValidationResponse/?uid=%s&token=%s" % (
        API_URL,
        context["uid"],
        context["token"],
    )

    params = {
        "user": context["user"],
        "organization": context["organization"],
        "url": urlString,
    }
    return params


def create_admin_success(context):
    params = {"url": CLIENT_URL, "uid": context["uid"], "token": context["token"]}
    return params


def create_admin_welcome(context):
    return {}


#######################################################################################################
#####################################     PW RESET      ###############################################
#####################################                   ###############################################
#######################################################################################################


def password_reset(context):
    params = {"url": CLIENT_URL, "uid": context["uid"], "token": context["token"]}
    return params


def password_reset_mooc(context):
    params = {"url": MOOC_CLIENT_URL, "uid": context["uid"], "token": context["token"]}
    return params


#######################################################################################################
#####################################     MISC.         ###############################################
#####################################                   ###############################################
#######################################################################################################


def publish_assignment(context):
    params = {
        "courseName": context["courseName"],
        "coursePeriod": context["coursePeriod"],
        "assignmentName": context["assignmentName"],
        "link": "%s/student/%s/%s/"
        % (
            CLIENT_URL,
            context["courseName"].replace(" ", "_"),
            context["coursePeriod"].replace(" ", "_"),
        ),
    }
    return params


def grader_reminder(context):
    params = {
        "courseName": context["courseName"],
        "coursePeriod": context["coursePeriod"],
        "assignmentName": context["assignmentName"],
        "num": context["num"],
    }
    return params


def partners_added(context):
    params = {
        "assignmentName": context["assignmentName"],
        "courseName": context["courseName"],
        "newPartnerEmail": context["newPartnerEmail"],
        "partnerEmails": context["partnerEmails"],
    }
    return params


def student_upload_receipt(context):
    params = {
        "assignmentName": context["assignmentName"],
        "courseName": context["courseName"],
        "students": context["students"],
        "dateUploadedHumanize": context["dateUploadedHumanize"],
        "dateUploadedTimestamp": context["dateUploadedTimestamp"],
    }

    return params


def student_feedback_notification(context):
    params = {
        "assignment_name": context["assignment_name"],
        "view_submission_url": context["view_submission_url"],
    }

    return params


def mooc_follow_up(context):
    return {}


#######################################################################################################
#############################     EMAILS TO USERS       ###############################################
#######################################################################################################
#######################################################################################################

USER_ACCESSIBLE_TEMPLATES = [
    "add_student",
    "add_grader",
    "add_admin",
    "publish_assignment",
    "grader_reminder",
    "regrades_reminder",
]

class RegradesReminderEmail(CodepostEmail):
    subject = "Regrades Reminder on CodePost"
    template = "emails/grader/regrade_reminder_template.html"

    def send_email(self, assignment:Assignment):
        """
        Sends an email to the user reminding them to check for regrades.
        """
        context = self.get_context(
            assignment=assignment,
        )

        html_content = render_to_string(self.template, context)

        email = EmailMessage(
            subject=self.subject,
            body=html_content,
            from_email=self.get_from_address(),
            to=[self.get_to_address()],
        )
        return self.send(email)

class GraderReminderEmail(CodepostEmail):
    subject = "Grader Reminder on CodePost"
    template = "emails/grader/reminder_template.html"

    def send_email(self, assignment:Assignment):
        """
        Sends an email to the user reminding them to grade submissions.
        """
        context = self.get_context(
            assignment=assignment,
        )

        html_content = render_to_string(self.template, context)

        email = EmailMessage(
            subject=self.subject,
            body=html_content,
            from_email=self.get_from_address(),
            to=[self.get_to_address()],
        )
        return self.send(email)

class PublishNewAssignmentEmail(CodepostEmail):
    subject = "New Assignment Published"
    template = "emails/assignments/publish_template.html"

    def send_email(self, assignment:Assignment):
        """
        Sends an email to the user notifying them that a new assignment has been published.
        """
        context = self.get_context(
            assignment=assignment,

        )   
        

        html_content = render_to_string(self.template, context)

        email = EmailMessage(
            subject=self.subject,
            body=html_content,
            from_email=self.get_from_address(),
            to=[self.get_to_address()],
        )
        return self.send(email)



# Tempalte schema:
# template (required): string corresponding to Sendgrid template
# generate_context (optional): build context variables from user (x) and course (y) and assignment (z) objects (optional)
# extra_parameters (optional): list of extra parameters to inject into context (optional)
# callbefore (optional): function that gates delivery of an email. returns true (send) or false (block send)
#    - if blank, will default to false
# test_parameters (optional): function to be used in place of
# generate_context when sending a test email (livemode = False)

# add_user_template = {
#     "template": "ADD_NEW",
#     "generate_context": lambda x, y, z: {
#         "uid": urlsafe_base64_encode(force_bytes(x.pk)),
#         "token": default_token_generator.make_token(x),
#     },
#     "test_parameters": lambda x, y, z: {
#         "uid": "xxx",
#         "token": "yyy",
#     },
# }

# USER_ACCESSIBLE_TEMPLATES_OLD = {
#     "add_student": {
#         "callbefore": lambda user, course, assn: (not user.is_active)
#         and (course in user.student_courses.all()),
#         "extra_parameters": {"type": "student"},
#         **add_user_template,
#     },
#     "add_grader": {
#         "callbefore": lambda user, course, assn: (not user.is_active)
#         and (course in user.grader_courses.all()),
#         "extra_parameters": {"type": "grader"},
#         **add_user_template,
#     },
#     "add_admin": {
#         "callbefore": lambda user, course, assn: (not user.is_active)
#         and (course in user.courseAdmin_courses.all()),
#         "extra_parameters": {"type": "admin"},
#         **add_user_template,
#     },
#     "publish_assignment": {
#         "template": "PUBLISH_ASSIGNMENT",
#         "callbefore": lambda user, course, assn: course in user.student_courses.all()
#         and assn.isReleased,
#     },
#     "grader_reminder": {
#         "template": "GRADER_REMINDER",
#         "callbefore": lambda user, course, assn: course in user.grader_courses.all()
#         and Submission.objects.filter(
#             grader=user, assignment=assn, isFinalized=False
#         ).count()
#         > 0,
#         "generate_context": lambda user, course, assn: {
#             "num": Submission.objects.filter(
#                 grader=user, assignment=assn, isFinalized=False
#             ).count(),
#         },
#         "test_parameters": lambda user, course, assn: {
#             "num": 4,
#         },
#     },
#     "regrades_reminder": {
#         "template": "REGRADES_REMINDER",
#         "callbefore": lambda user, course, assn: course in user.grader_courses.all()
#         and Submission.objects.filter(
#             grader=user, assignment=assn, questionIsOpen=True
#         ).count()
#         > 0,
#         "generate_context": lambda user, course, assn: {
#             "num": Submission.objects.filter(
#                 grader=user, assignment=assn, questionIsOpen=True
#             ).count(),
#         },
#         "test_parameters": lambda user, course, assn: {
#             "num": 4,
#         },
#     },
# }
