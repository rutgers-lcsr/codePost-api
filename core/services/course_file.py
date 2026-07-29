# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""CourseFile create/update with copy-on-write content sharing.

Course cloning links the cloned course's CourseFile row to the SAME CourseFileContent
(same bytes, same public flag, same token → the public URL keeps working in cloned
markdown). Writes to that shared state must come through here: a write to a shared
content first detaches the acting row onto its own fresh content (fresh token), so the
other courses' URLs never break.
"""
from django.db import transaction

from core.models import CourseFile, CourseFileContent, validate_data_uri_mime


def create_course_file(*, course, name, data='', extension='', path=None,
                       is_public=False, description='', student_visible=False) -> CourseFile:
    """Create a CourseFile with its own (exclusive) content row."""
    cf = CourseFile(course=course, name=name, data=data, extension=extension, path=path,
                    description=description, studentVisible=student_visible)
    cf.save()  # bootstrap moves data onto a fresh private content
    if is_public:
        cf.content.isPublic = True
        cf.content.save()
    return cf


def update_course_file_content(cf: CourseFile, *, data=None, is_public=None) -> CourseFile:
    """Apply a data and/or isPublic change to a CourseFile, copy-on-write.

    - No-op values are dropped first: the UI PATCHes whole objects, and an unchanged
      echo must not trigger a split.
    - Shared content (another course's row points at it): detach THIS row to a new
      content carrying the change; the other rows keep the original content and token.
    - Exclusive content: mutate in place — identical to the old single-course behavior,
      including CourseFileContent.save()'s rotate-token-on-unpublish revocation.
    """
    content = cf.content
    if data is not None and data == content.data:
        data = None
    if is_public is not None and is_public == content.isPublic:
        is_public = None
    if data is None and is_public is None:
        return cf
    if data is not None and data.startswith('data:'):
        validate_data_uri_mime(cf.name, data)

    shared = content.files.exclude(pk=cf.pk).exists()
    if shared:
        with transaction.atomic():
            new_content = CourseFileContent.objects.create(
                data=content.data if data is None else data,
                isPublic=content.isPublic if is_public is None else is_public)
            cf.content = new_content
            cf.save()
    else:
        if data is not None:
            content.data = data
        if is_public is not None:
            content.isPublic = is_public
        content.save()
    return cf
