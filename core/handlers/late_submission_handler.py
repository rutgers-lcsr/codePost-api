# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from core.models import Course, Assignment, Submission, Comment, CommentTag


def date_diff_days(first, second):
  """
  Difference in days between two DateTimeFields
  """
  return (second - first).days + 1


def date_diff_hours(first, second):
  """
  Difference in hours between two DateTimeFields
  """
  return (second - first).total_seconds() / 3600


def late_day_credits_available_by_student(user, assignment):
  """
  Return the number of Late Day Credits that a student still has available.
  Exclude the current assignment.
  """
  if assignment.course.lateDayCreditsAllowable == None or assignment.course.lateDayCreditsAllowable == 0:
    return 0

  submissions = Submission.objects.filter(students=user, assignment__course=assignment.course)

  used_late_day_count = 0
  for submission in submissions:
    if submission.assignment != assignment:
      used_late_day_count += submission.lateDayCreditsUsed

  return assignment.course.lateDayCreditsAllowable - used_late_day_count


class LateSubmissionHandler:

  # ****** HARDCODED CONSTANTS ******
  GRACE_PERIOD_HOURS = 2
  LATE_DAY_CREDIT_PER_ASSIGNMENT_BUDGET = 2
  # ***** ***** ***** ***** ***** ***

  def __init__(self, submission, students=None):
    self.submission = submission
    self.assignment = submission.assignment
    self.course = submission.assignment.course
    self.students = students

    if self.assignment.uploadDueDate == None:
      self.real_days_late = 0
    else:
      self.real_days_late = date_diff_days(self.assignment.uploadDueDate, self.submission.dateUploaded)

    self.late_day_credits_to_use = self.__late_day_credits_to_use()

  def is_late(self):
    """
    Use Grace Period to decide whether submission is late
    """
    if self.real_days_late == 1:
      if date_diff_hours(self.assignment.uploadDueDate, self.submission.dateUploaded) < self.GRACE_PERIOD_HOURS:
        return False
      else:
        return True
    return self.real_days_late > 0

  def __get_author(self):
    """
    The author of the automatically placed comment will be
    the first admin in the course.
    """
    return self.course.courseAdmins.all().first()

  def __late_day_credits_to_use(self):
    """
    Returns the number of Late Day Credits to use.

    Never use more Late Day Credits than the Per_Assignment_Budget (hardcoded)
    or the number of days late.
    """
    if not self.is_late():
      return 0

    if len(self.assignment.lateDeductions) == 0 or sum(self.assignment.lateDeductions) == 0:
      return 0

    credits_to_use = self.late_day_credits_available()

    if credits_to_use > self.LATE_DAY_CREDIT_PER_ASSIGNMENT_BUDGET:
      credits_to_use = self.LATE_DAY_CREDIT_PER_ASSIGNMENT_BUDGET

    if credits_to_use > self.real_days_late:
      credits_to_use = self.real_days_late

    return credits_to_use

  def calculated_days_late(self):
    """
    Returns the number of days late minus the number of Late Day Credits used
    """
    return self.real_days_late - self.late_day_credits_to_use

  def late_day_credits_available(self):
    """
    For partner submissions, calculate late day credits available as the
    maximum number available between the partners.

    Example: [student1 (2 credits), student2 (3 credits)] => 3 credits available
    """
    credits_available = 0

    # Optionally declare students in case we are handling an unsaved Submission object
    if self.students == None:
      students = self.submission.students.all()
    else:
      students = self.students

    for student in students:
      this_student_credits_available = late_day_credits_available_by_student(student, self.assignment)
      if this_student_credits_available > credits_available:
        credits_available = this_student_credits_available

    return credits_available

  def get_points(self):
    """
    Assignment.lateDeductions is an array of integers.

    Example:
      Assignment.lateDeductions = [2, 4, 8] means

      1 day late   = 2 points off
      2 days late  = 4 points off
      3+ days late = 8 points off
    """
    if len(self.assignment.lateDeductions) == 0:
      return 0

    if self.calculated_days_late() == 0:
      return 0

    if self.calculated_days_late() > len(self.assignment.lateDeductions):
      return self.assignment.lateDeductions[-1]

    return self.assignment.lateDeductions[self.calculated_days_late() - 1]

  def __create_late_comment(self):
    """
    Create a special comment with tag-type 'late'
    """
    str_days_late = "Days Late:                {}\n".format(self.real_days_late)
    str_credits_used = ""

    if self.course.lateDayCreditsAllowable != None:
      str_credits_used = "Late Credits Used:        {}\nDays Late (After Credit): {}".format(
          self.late_day_credits_to_use, self.calculated_days_late())

    text = """
```
{}{}
```
""".format(str_days_late, str_credits_used)

    file = self.submission.files.order_by('name', 'created').first()

    points = self.get_points()

    late_tag = CommentTag.objects.get(label="late")
    comment = Comment.objects.create(text=text, author=self.__get_author(), file=file, startChar=0,
                                     endChar=1, startLine=1, endLine=1, pointDelta=points, rubricComment=None)
    comment.tags.set([late_tag.id])
    comment.save()
    return

  def __delete_late_comments(self):
    """
    Delete all submission comments with tag-type 'late'
    """
    for file in self.submission.files.all():
      for comment in file.comments.all():
        if 'late' in comment.tags.values_list('label', flat=True):
          comment.delete()

  def handle(self):
    if self.assignment.uploadDueDate != None and self.is_late() and (len(self.assignment.lateDeductions) > 0 or self.course.lateDayCreditsAllowable != None):

      # Update Submission
      self.submission.lateDayCreditsUsed = self.late_day_credits_to_use
      self.submission.save()

      # Delete old Late comments
      self.__delete_late_comments()

      # Create new Late comment
      self.__create_late_comment()
