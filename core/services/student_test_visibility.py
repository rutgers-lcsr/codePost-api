# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""
The single decision about which SubmissionTests a student may see.

Used by GET /submissionTests/{id}/ (via SubmissionTestPermissions),
GET /submissions/{id}/submissionTests/ and GET /submissions/{id}/testResults/.
"""
from django.core.exceptions import ObjectDoesNotExist

from autograder.run import filterExposedSubmissionTests
from core.permissions.helpers import testResultsVisibleForSubmission


def tests_visible_to_student(submission):
  """SubmissionTests of `submission` a student may see, before hidden-test masking.

  Once grading results are revealed (testResultsVisibleForSubmission) every test is
  included; until then only TestCase.exposed ones, capped by maxExposedFailedTests."""
  tests = list(submission.tests.all())
  if testResultsVisibleForSubmission(submission):
    return tests
  try:
    maxFailedTests = submission.assignment.environment.maxExposedFailedTests
  except ObjectDoesNotExist:  # no Environment yet: no exposure cap
    maxFailedTests = None
  return filterExposedSubmissionTests(tests, maxFailedTests)[0]


def mask_hidden_tests(submission, tests, rows):
  """Replace the serialized rows of hidden tests with one synthetic per-category summary
  each, so students get pass count + point impact but never the test's name, logs or
  explanation. `rows` are the serialized `tests`, in the same order."""
  hidden_by_category = {}
  visible_rows = []
  for st, row in zip(tests, rows):
    if st.testCase.hidden:
      hidden_by_category.setdefault(st.testCase.testCategory_id, []).append(st)
    else:
      visible_rows.append(row)

  synthetic_rows = []
  for cat_id, hidden_tests in hidden_by_category.items():
    passed_count = sum(1 for t in hidden_tests if t.passed)
    total_count = len(hidden_tests)
    points_earned = sum((t.score or 0) for t in hidden_tests)
    points_total = sum((t.maxScore or 0) for t in hidden_tests)
    synthetic_rows.append({
      # Negative id sentinels distinguish synthetic summary rows from real
      # SubmissionTests; clients should treat hiddenSummary != null as the
      # source of truth, not the id.
      'id': -cat_id,
      'submission': submission.id,
      'testCase': None,
      'testCategory': cat_id,
      'logs': '',
      'passed': passed_count == total_count and total_count > 0,
      'created': None,
      'modified': None,
      'isError': False,
      'score': points_earned,
      'maxScore': points_total,
      'results': None,
      'hiddenSummary': {
        'label': 'Hidden tests',
        'passedCount': passed_count,
        'totalCount': total_count,
        'pointsEarned': points_earned,
        'pointsTotal': points_total,
      },
    })
  return visible_rows + synthetic_rows
