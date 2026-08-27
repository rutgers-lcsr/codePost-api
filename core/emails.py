# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from abc import ABC, abstractmethod
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from zoneinfo import ZoneInfo
from codepost.settings import (
    CLIENT_URL,
    API_URL,
    DEFAULT_EMAIL_FROM,
    OVERRIDE_EMAIL,
    ADMINS,
    SUPPORT_URL,
    TESTING
)

from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes

import logging
from core.handlers.submission_version_handler import SubmissionVersionHandler
from core.logging import logEvent
from core.models import Assignment, Submission, User


class CodepostEmail(ABC):
    subject = "CodePost Notification"
    template = "emails/base_template.html"

    def __init__(self, user:User|None= None):
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
            "api_url": API_URL,
            "support_url": SUPPORT_URL,
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
        """
        Returns the email address to which the email should be sent.
        If OVERRIDE_EMAIL is set, it will return that email address.
        """
        if OVERRIDE_EMAIL:
            return OVERRIDE_EMAIL

        if not self.user:
            logEvent(event="Email send failed", message="No user provided for email", level=logging.ERROR)
            raise ValueError("No user provided for email")

        if self.user.email:
            return self.user.email

        if self.user.profile.organization and self.user.profile.organization.email:
            return self.user.profile.organization.email

        raise ValueError("User does not have an email address set.")
    
    def get_from_address(self):
        """
        Returns the email address from which the email should be sent.
        """
        return self.from_email

    def get_admin_emails(self):
        """
        Returns a list of org staff emails for the organization, plus CodePost admins.
        If the user is not part of an organization, it returns only CodePost admins.
        """
        CODEPOST_ADMINS = list(map(lambda x: x[1], ADMINS))

        if not self.user or not self.user.profile.organization:
            return CODEPOST_ADMINS

        org_name = self.user.profile.organization.name

        org_staff = User.objects.filter(
            profile__organization__name=org_name,
            profile__isOrgStaff=True
        ).values_list('email', flat=True)

        return list(org_staff) + CODEPOST_ADMINS

    def get_codepost_admins(self):
        return list(map(lambda x: x[1], ADMINS))

    def send(self, email:EmailMessage, type:str = "html"):
        """
        Sends the email using the Django EmailMessage class.
        """
        if TESTING:
            return None
        try:
            email.content_subtype = type 
            logEvent(event="Email Sent", message="{} sent to {}".format(self.subject, self.get_to_address(),))
            email.send()
        except Exception as e:
            # Will log out the error in the Django logs
            logEvent(event="Email Failed", message=str(e), level=logging.ERROR, skip_email=True)
            return None
class CodepostAPIErrorEmail(CodepostEmail):
    subject = "CodePost API Error Notification"
    template = "emails/api_error_template.html"

    def send_email(self, error_message:str, error_details:str):
        """
        Sends an email to the CodePost admins notifying them of an API error.
        """
        context = self.get_context(
            error_message=error_message,
            error_details=error_details,
        )

        html_content = render_to_string(self.template, context)

        email = EmailMessage(
            subject=self.subject,
            body=html_content,
            from_email=self.get_from_address(),
            to=self.get_codepost_admins(),
        )
        return self.send(email)

class UserAddedToCourseEmail(CodepostEmail):
    subject = "You have been added to a course on CodePost"
    template = "emails/user/add_to_course_template.html"

    def send_email(self, course_name:str, course_period:str, user_type:str, force_send:bool=False):
        """
        Sends an email to the user notifying them that they have been added to a course.
        """
        assert self.user is not None
        
        # Check if organization desires to suppress welcome emails
        # force_send can override this (e.g. if Course.emailNewUsers is explicitly set)
        if self.user.profile.organization and hasattr(self.user.profile.organization, 'send_welcome_email'):
             if not self.user.profile.organization.send_welcome_email and not force_send:
                 return None

        # Determine if we should send the "Active User" template or the "Activate Account" template
        # Users in SSO Orgs are active, but might not have passwords set. 
        # But if they are SSO, they don't need to "activate" via email token.
        is_sso = False
        if self.user.profile.organization and hasattr(self.user.profile.organization, 'sso_enabled'):
            is_sso = self.user.profile.organization.sso_enabled

        if self.user.is_active and (self.user.profile.isPasswordSet or is_sso):
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
        assert self.user is not None
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
        assert self.user is not None
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
        assert self.user is not None
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
        assert self.user is not None
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
            to=self.get_admin_emails(),
        )

        return self.send(email)
class NewAdminActivationEmail(CodepostEmail):
    subject = "Your CodePost account has been approved!"
    template = "emails/admin/activation_template.html"

    def send_email(self, organization_name:str):
        """
        Sends an email to the user notifying them that they have been activated as an admin.
        """
        assert self.user is not None
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
        assert self.user is not None
        tz = ZoneInfo(submission.assignment.course.timezone)
        dateUploaded = submission.dateUploaded.astimezone(tz)

        dateUploadedHumanize = dateUploaded.strftime("%A, %m-%d-%Y %H:%M:%S")
        dateUploadedTimestamp = dateUploaded.strftime("%Y%m%d_%H%M")
        
        files = SubmissionVersionHandler(submission).encoded_zip()
        zip_name = "{}_{}_{}.zip".format(self.get_to_address(), submission.id, dateUploaded.strftime("%Y-%m-%d_%H-%M-%S"))
        
        attachments = [
            (zip_name, files, "application/zip")
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

        partner_emails = ", ".join(list(submission.students.all().values_list('email', flat=True)))

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


class NewOrgAdminRequestEmail(CodepostEmail):
    """
    Email sent to CodePost staff when a user requests to create a NEW organization
    and become a course admin.
    """
    subject = "New Organization Admin Request on CodePost"
    template = "emails/admin/new_org_admin_request_template.html"

    def send_email(self, organization_name:str):
        assert self.user is not None
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
            to=self.get_codepost_admins(),
        )

        return self.send(email)


class ExistingOrgAdminRequestEmail(CodepostEmail):
    """
    Email sent to Org Staff AND CodePost staff when a user requests to become
    a course admin in an EXISTING organization.
    """
    subject = "New Course Admin Request on CodePost"
    template = "emails/admin/existing_org_admin_request_template.html"

    def send_email(self, organization_name:str):
        assert self.user is not None
        context = self.get_context(
            organization=organization_name,
            uid=urlsafe_base64_encode(force_bytes(self.user.pk)),
            token=default_token_generator.make_token(self.user),
        )

        html_content = render_to_string(self.template, context)

        # Send to both org staff and codepost admins
        recipients = self.get_admin_emails()

        email = EmailMessage(
            subject=self.subject,
            body=html_content,
            from_email=self.get_from_address(),
            to=recipients,
        )

        return self.send(email)


class PendingConfirmationEmail(CodepostEmail):
    """
    Email sent to the user confirming their request has been received and is pending approval.
    """
    subject = "Your codePost Admin Request is Pending"
    template = "emails/admin/pending_confirmation_template.html"

    def send_email(self, organization_name:str, is_new_org:bool=False):
        context = self.get_context(
            organization=organization_name,
            is_new_org=is_new_org,
        )

        html_content = render_to_string(self.template, context)

        email = EmailMessage(
            subject=self.subject,
            body=html_content,
            from_email=self.get_from_address(),
            to=[self.get_to_address()],
        )

        return self.send(email)
