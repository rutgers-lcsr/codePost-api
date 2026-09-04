# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""The in-process dispatcher's security boundaries."""
import factory
import pytest
from django.db.models.signals import post_save

from core.agent import errors
from core.agent.dispatch import Dispatcher, _REPLAYED_META


@pytest.fixture
def course(db):
    from core.tests.factories import CourseFactory
    with factory.django.mute_signals(post_save):
        return CourseFactory(name="cs303", period="f2026", organization__name="TestOrg")


class TestHeaderAllowlist:
    """Which request headers get replayed is a security boundary, so it is pinned.

    Forwarding Cookie would let SessionAuthentication succeed on the synthetic
    request, which in turn switches on DRF's CSRF enforcement and would let an
    agent inherit a browser session it was never given.
    """

    def test_only_authorization_is_replayed(self):
        assert _REPLAYED_META == ('HTTP_AUTHORIZATION',)

    def test_cookie_is_not_replayed(self, course):
        d = Dispatcher(
            {'HTTP_AUTHORIZATION': 'CourseKey cpk_1_abc',
             'HTTP_COOKIE': 'sessionid=stolen',
             'HTTP_X_FORWARDED_FOR': '10.0.0.1'},
            course_id=course.id)
        assert d._creds == {'HTTP_AUTHORIZATION': 'CourseKey cpk_1_abc'}


class TestScopePostcondition:
    """Defence in depth: tools compose several calls and pass ids between them."""

    def test_matching_course_passes(self, course):
        d = Dispatcher({}, course_id=course.id)
        d.assert_in_scope(course.id, what='thing')      # does not raise

    def test_other_course_raises(self, course):
        d = Dispatcher({}, course_id=course.id)
        with pytest.raises(errors.ToolError) as exc:
            d.assert_in_scope(course.id + 1, what='assignment 99')
        assert exc.value.code == 'NOT_IN_SCOPE'
        assert exc.value.retryable is False

    def test_unresolvable_course_fails_closed(self, course):
        """No discernible course means deny, not allow."""
        d = Dispatcher({}, course_id=course.id)
        with pytest.raises(errors.ToolError):
            d.assert_in_scope(None, what='mystery object')
