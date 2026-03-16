# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from django.db import models
from django.contrib.auth.models import User
from django.utils.timezone import now
from typing import TYPE_CHECKING



class Event(models.Model):
    EVENT_TYPE_CHOICES = [
        ('audit', 'Audit'),
        ('activity', 'Activity'),
    ]

    created = models.DateTimeField(auto_now_add=True, db_index=True)
    updated = models.DateTimeField(auto_now=True)

    category = models.CharField(max_length=255, default="uncategorized")
    type = models.CharField(max_length=20, choices=EVENT_TYPE_CHOICES, default='activity', db_index=True)
    description = models.CharField(max_length=255)
    courseID = models.IntegerField(null=True)
    user = models.CharField(max_length=255, null=True)
    meta = models.TextField(default="")

    def save(self, *args, **kwargs):
        return super(Event, self).save(*args, **kwargs)


class TrackedAutograderRun(models.Model):
    modified = models.DateTimeField(default=now)

    started = models.DateTimeField(editable=False, null=True, blank=True)
    ended = models.DateTimeField(editable=False, null=True, blank=True)
    duration = models.IntegerField(null=True, blank=True)

    errors = models.TextField(blank=True)

    test_case_set = models.CharField(
        max_length=255,
        choices=(
            ("all", "all"),
            ("partial", "partial"),
        ),
    )

    run_by_role = models.CharField(
        max_length=255,
        choices=(
            ("instructor", "instructor"),
            ("student", "student"),
            ("unknown", "unknown"),
        ),
        default="unknown",
    )

    run_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    submission = models.ForeignKey(
        "core.Submission", on_delete=models.SET_NULL, null=True, blank=True
    )

    assignment = models.ForeignKey(
        "core.Assignment", on_delete=models.SET_NULL, null=True, blank=True
    )

    def __str__(self):
        return (
            f"{self.id} {self.assignment.course.organization} (COMPLETED)"
            if self.duration
            else f"{self.id} {self.assignment.course.organization} (IN PROGRESS)"
        )

    def save(self, *args, **kwargs):
        if self.started and self.ended:
            _duration = (self.ended - self.started).total_seconds()
            if _duration == 0:
                _duration = 1
                self.errors = (
                    self.errors
                    + "-> Duration was less than 1 second "
                    + str(self.started)
                    + " | "
                    + str(self.ended)
                )
            self.duration = _duration
        return super(TrackedAutograderRun, self).save(*args, **kwargs)

    class Meta:
        ordering = ["-ended"]
