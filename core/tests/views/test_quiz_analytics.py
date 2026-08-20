# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""Tests for the course-level quiz grading-progress aggregate
(GET /courses/{id}/quizGradingProgress/)."""
import pytest
from rest_framework import status

# Reuse the quiz-taking course fixture and the shared quiz builders.
from core.tests.views.test_quiz_attempts import taking_setup  # noqa: F401  (pytest fixture)
from core.tests.views.quiz_helpers import _add, _bank, _essay, _mc, _quiz


def _essay_quiz(course, title):
    bank = _bank(course)
    quiz = _quiz(course, title=title)
    _add(quiz, _mc(course, bank), sortKey=0)     # 2 pts auto — never counts as manual
    _add(quiz, _essay(course, bank), sortKey=1)  # 5 pts manual
    return quiz


def _submit(api_client, quiz, student):
    """Student answers both questions and submits; returns (attempt_id, essay_response_id)."""
    api_client.force_authenticate(user=student)
    start = api_client.post('/quizAttempts/', {'quiz': quiz.id}, format='json')
    assert start.status_code == status.HTTP_201_CREATED
    essay_id = None
    for r in start.data['responses']:
        if r['question']['questionType'] == 'essay':
            essay_id = r['id']
            api_client.patch(f"/quizAttempts/{start.data['id']}/saveAnswer/",
                             {'response': r['id'], 'answerText': 'Because.'}, format='json')
    done = api_client.post(f"/quizAttempts/{start.data['id']}/submit/", {}, format='json')
    assert done.status_code == status.HTTP_200_OK
    return start.data['id'], essay_id


def _grade(api_client, grader, attempt_id, response_id, points='3'):
    api_client.force_authenticate(user=grader)
    resp = api_client.post(f'/quizAttempts/{attempt_id}/gradeResponse/',
                           {'response': response_id, 'pointsEarned': points}, format='json')
    assert resp.status_code == status.HTTP_200_OK


@pytest.mark.django_db
class TestQuizGradingProgress:
    def _fetch(self, api_client, taking_setup):
        api_client.force_authenticate(user=taking_setup['admin'])
        resp = api_client.get(f"/courses/{taking_setup['course'].id}/quizGradingProgress/")
        assert resp.status_code == status.HTTP_200_OK
        return resp.data

    def test_counts_per_grader_and_quiz(self, api_client, taking_setup):
        course = taking_setup['course']
        graders = list(course.graders.all()[:2])
        quiz1 = _essay_quiz(course, 'Quiz One')
        quiz2 = _essay_quiz(course, 'Quiz Two')

        a1, e1 = _submit(api_client, quiz1, taking_setup['students'][0])
        a2, e2 = _submit(api_client, quiz1, taking_setup['students'][1])
        a3, e3 = _submit(api_client, quiz2, taking_setup['students'][0])
        _grade(api_client, graders[0], a1, e1)   # grader0: 1 on quiz1
        _grade(api_client, graders[1], a3, e3)   # grader1: 1 on quiz2; a2/e2 stays pending

        data = self._fetch(api_client, taking_setup)
        by_id = {q['id']: q for q in data['quizzes']}
        assert by_id[quiz1.id] == {'id': quiz1.id, 'title': 'Quiz One',
                                   'totalManual': 2, 'graded': 1, 'pending': 1}
        assert by_id[quiz2.id] == {'id': quiz2.id, 'title': 'Quiz Two',
                                   'totalManual': 1, 'graded': 1, 'pending': 0}
        assert data['pendingUngraded'] == 1

        rows = {g['grader']: g for g in data['graders']}
        assert rows[graders[0].email]['totalGraded'] == 1
        assert rows[graders[0].email]['perQuiz'] == {quiz1.id: 1}
        assert rows[graders[0].email]['lastGradedAt'] is not None
        assert rows[graders[1].email]['perQuiz'] == {quiz2.id: 1}

    def test_requires_view_analytics(self, api_client, taking_setup):
        course = taking_setup['course']
        url = f'/courses/{course.id}/quizGradingProgress/'
        # Plain graders (who CAN grade by default) still don't see peers' throughput.
        api_client.force_authenticate(user=course.graders.first())
        assert api_client.get(url).status_code == status.HTTP_403_FORBIDDEN
        # The explicit quiz-grader role doesn't help either — this is an admin dashboard.
        course.quizGraders.add(course.graders.first())
        assert api_client.get(url).status_code == status.HTTP_403_FORBIDDEN
        api_client.force_authenticate(user=taking_setup['students'][0])
        assert api_client.get(url).status_code == status.HTTP_403_FORBIDDEN
        api_client.force_authenticate(user=taking_setup['admin'])
        assert api_client.get(url).status_code == status.HTTP_200_OK

    def test_excludes_drafts_and_in_progress_attempts(self, api_client, taking_setup):
        course = taking_setup['course']
        draft = _essay_quiz(course, 'Draft')
        draft.isPublished = False
        draft.save()
        live = _essay_quiz(course, 'Live')
        # An in-progress attempt (started, not submitted) must not count.
        api_client.force_authenticate(user=taking_setup['students'][0])
        start = api_client.post('/quizAttempts/', {'quiz': live.id}, format='json')
        assert start.status_code == status.HTTP_201_CREATED

        data = self._fetch(api_client, taking_setup)
        assert [q['id'] for q in data['quizzes']] == [live.id]
        assert data['quizzes'][0]['totalManual'] == 0
        assert data['pendingUngraded'] == 0

    def test_reopen_moves_count_back_to_pending(self, api_client, taking_setup):
        course = taking_setup['course']
        quiz = _essay_quiz(course, 'Reopenable')
        attempt_id, essay_id = _submit(api_client, quiz, taking_setup['students'][0])
        _grade(api_client, taking_setup['admin'], attempt_id, essay_id)
        assert self._fetch(api_client, taking_setup)['quizzes'][0]['graded'] == 1

        api_client.force_authenticate(user=taking_setup['admin'])
        reopen = api_client.post(f'/quizAttempts/{attempt_id}/reopenResponse/',
                                 {'response': essay_id}, format='json')
        assert reopen.status_code == status.HTTP_200_OK
        data = self._fetch(api_client, taking_setup)
        assert data['quizzes'][0] == {'id': quiz.id, 'title': 'Reopenable',
                                      'totalManual': 1, 'graded': 0, 'pending': 1}
        assert data['graders'] == []
        assert data['pendingUngraded'] == 1

    def test_empty_course_shape(self, api_client, taking_setup):
        quiz = _essay_quiz(taking_setup['course'], 'Untouched')
        data = self._fetch(api_client, taking_setup)
        assert data['quizzes'] == [{'id': quiz.id, 'title': 'Untouched',
                                    'totalManual': 0, 'graded': 0, 'pending': 0}]
        assert data['graders'] == []
        assert data['pendingUngraded'] == 0
