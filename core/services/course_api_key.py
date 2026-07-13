# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from django.contrib.auth.models import User

from core.models import Course


def get_or_create_course_service_user(course: Course) -> User:
    """Return (or create) the service-account user for *course*.

    The user is added as a courseAdmin so existing permission helpers
    work without special-casing.  The account has an unusable password
    and ``Profile.isServiceAccount = True``.
    """
    username = f"course-{course.id}-api"
    email = f"course-{course.id}-api@codepost.io"

    user, created = User.objects.get_or_create(
        username=username,
        defaults={"email": email, "is_active": True},
    )

    if created:
        user.set_unusable_password()
        user.save(update_fields=["password"])

    # Ensure profile is flagged as service account (signal auto-creates Profile)
    profile = user.profile
    if not profile.isServiceAccount:
        profile.isServiceAccount = True
        profile.organization = course.organization
        profile.save()

    # Ensure the user is a courseAdmin
    if not course.courseAdmins.filter(pk=user.pk).exists():
        course.courseAdmins.add(user)

    return user
