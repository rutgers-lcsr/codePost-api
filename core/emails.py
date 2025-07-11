from codepost.settings import (
    SENDGRID_API_KEY,
    CLIENT_URL,
    MOOC_CLIENT_URL,
    API_URL,
    SENDGRID_SANDBOX,
    SENDGRID_OVERRIDE_EMAIL,
)
import sendgrid
from sendgrid.helpers.mail import *

from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes

from django import forms

from core.models import Submission

from django.conf import settings


def send_email_sendgrid(from_email, to_email, params, templateID, attachments=None):
    sg = sendgrid.SendGridAPIClient(apikey=SENDGRID_API_KEY)
    if SENDGRID_OVERRIDE_EMAIL:
        to_email_to_use = SENDGRID_OVERRIDE_EMAIL
    else:
        to_email_to_use = to_email

    data = {
        "personalizations": [
            {"to": [{"email": to_email_to_use}], "dynamic_template_data": params}
        ],
        "from": {"name": "codePost Team", "email": from_email},
        "template_id": templateID,
        "attachments": attachments,
    }

    if SENDGRID_SANDBOX:
        data["mail_settings"] = {"sandbox_mode": {"enable": True}}

    if not settings.TESTING:
        response = sg.client.mail.send.post(request_body=data)
        return response
    else:
        return None


def get_email_params(identifier, context):
    if identifier == "ADD_NEW":
        return add_new_user_template(context)
    elif identifier == "ADD_EXISTING":
        return add_existing_user_template(context)
    elif identifier == "UPGRADE_ACTIVE":
        return upgrade_active_user_template(context)
    elif identifier == "UPGRADE_INACTIVE":
        return upgrade_inactive_user_template(context)
    elif identifier == "UPGRADE_DOESNOTEXIST":
        return upgrade_non_user(context)
    elif identifier == "JOIN_ACTIVE":
        return join_active_user_template(context)
    elif identifier == "JOIN_INACTIVE":
        return join_inactive_user_template(context)
    elif identifier == "JOIN_INACTIVE_MOOC":
        return join_inactive_user_mooc_template(context)
    elif identifier == "JOIN_DOESNOTEXIST":
        return join_non_user(context)
    elif identifier == "CREATE_ALREADY_ADMIN":
        return create_already_admin(context)
    elif identifier == "CREATE_ORGANIZATION_CHANGE":
        return create_organization_change(context)
    elif identifier == "CREATE_VALIDATION":
        return validation_check_to_codepost_team(context)
    elif identifier == "CREATE_SUCCESS":
        return create_admin_success(context)
    elif identifier == "CREATE_WELCOME":
        return create_admin_welcome(context)
    elif identifier == "PASSWORD_RESET":
        return password_reset(context)
    elif identifier == "PASSWORD_RESET_MOOC":
        return password_reset_mooc(context)
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
    return SENDGRID_TEMPLATE_MAP.get(identifier, None)


#######################################################################################################
#####################################      ROSTER       ###############################################
#####################################                   ###############################################
#######################################################################################################


def add_existing_user_template(context):
    """
    Parameters:
    type : {'student', 'grader', 'admin'}
    courseName : string
    coursePeriod : string
    """
    if context["type"] == "student":
        role = "a student"
        linkSentence = "To view your reviewed coursework, visit"
        link = "%s/student/%s/%s/" % (
            CLIENT_URL,
            context["courseName"].replace(" ", "_"),
            context["coursePeriod"].replace(" ", "_"),
        )
    elif context["type"] == "grader":
        role = "a grader"
        linkSentence = "To view your grader dashboard, visit"
        link = "%s/grader/%s/%s/" % (
            CLIENT_URL,
            context["courseName"].replace(" ", "_"),
            context["coursePeriod"].replace(" ", "_"),
        )
    elif context["type"] == "admin":
        role = "an administrator"
        linkSentence = "To view your administrator dashboard, visit"
        link = "%s/course-admin/%s/%s/" % (
            CLIENT_URL,
            context["courseName"].replace(" ", "_"),
            context["coursePeriod"].replace(" ", "_"),
        )
    else:
        return None

    params = {
        "role": role,
        "linkSentence": linkSentence,
        "link": link.replace(" ", "_"),
        "course": "%s | %s" % (context["courseName"], context["coursePeriod"]),
    }
    return params


def add_new_user_template(context):
    if context["type"] == "student":
        role = "a student"
    elif context["type"] == "grader":
        role = "a grader"
    elif context["type"] == "admin":
        role = "an administrator"
    else:
        return None

    params = {
        "role": role,
        "course": "%s | %s" % (context["courseName"], context["coursePeriod"]),
        "url": CLIENT_URL,
        "uid": context["uid"],
        "token": context["token"],
    }
    return params


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

# Tempalte schema:
# template (required): string corresponding to Sendgrid template
# generate_context (optional): build context variables from user (x) and course (y) and assignment (z) objects (optional)
# extra_parameters (optional): list of extra parameters to inject into context (optional)
# callbefore (optional): function that gates delivery of an email. returns true (send) or false (block send)
#    - if blank, will default to false
# test_parameters (optional): function to be used in place of
# generate_context when sending a test email (livemode = False)

add_user_template = {
    "template": "ADD_NEW",
    "generate_context": lambda x, y, z: {
        "uid": urlsafe_base64_encode(force_bytes(x.pk)),
        "token": default_token_generator.make_token(x),
    },
    "test_parameters": lambda x, y, z: {
        "uid": "xxx",
        "token": "yyy",
    },
}

USER_ACCESSIBLE_TEMPLATES = {
    "add_student": {
        "callbefore": lambda user, course, assn: (not user.is_active)
        and (course in user.student_courses.all()),
        "extra_parameters": {"type": "student"},
        **add_user_template,
    },
    "add_grader": {
        "callbefore": lambda user, course, assn: (not user.is_active)
        and (course in user.grader_courses.all()),
        "extra_parameters": {"type": "grader"},
        **add_user_template,
    },
    "add_admin": {
        "callbefore": lambda user, course, assn: (not user.is_active)
        and (course in user.courseAdmin_courses.all()),
        "extra_parameters": {"type": "admin"},
        **add_user_template,
    },
    "publish_assignment": {
        "template": "PUBLISH_ASSIGNMENT",
        "callbefore": lambda user, course, assn: course in user.student_courses.all()
        and assn.isReleased,
    },
    "grader_reminder": {
        "template": "GRADER_REMINDER",
        "callbefore": lambda user, course, assn: course in user.grader_courses.all()
        and Submission.objects.filter(
            grader=user, assignment=assn, isFinalized=False
        ).count()
        > 0,
        "generate_context": lambda user, course, assn: {
            "num": Submission.objects.filter(
                grader=user, assignment=assn, isFinalized=False
            ).count(),
        },
        "test_parameters": lambda user, course, assn: {
            "num": 4,
        },
    },
    "regrades_reminder": {
        "template": "REGRADES_REMINDER",
        "callbefore": lambda user, course, assn: course in user.grader_courses.all()
        and Submission.objects.filter(
            grader=user, assignment=assn, questionIsOpen=True
        ).count()
        > 0,
        "generate_context": lambda user, course, assn: {
            "num": Submission.objects.filter(
                grader=user, assignment=assn, questionIsOpen=True
            ).count(),
        },
        "test_parameters": lambda user, course, assn: {
            "num": 4,
        },
    },
}
