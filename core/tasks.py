# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from celery import shared_task
from core.models import Course
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)

@shared_task
def delete_expired_courses():
    """
    Deletes courses whose expiration_date has passed.
    """
    now = timezone.now()
    expired_courses = Course.objects.filter(expiration_date__lte=now)
    count = expired_courses.count()
    
    if count > 0:
        logger.info(f"Deleting {count} expired courses")
        # Depending on how cascade delete works, this might take a while or fail if there are too many related objects.
        # But for test courses it should be fine.
        expired_courses.delete()
    else:
        logger.info("No expired courses found")
