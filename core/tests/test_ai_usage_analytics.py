# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial Licensed, included with this software.
"""
Tests for the AI Usage Analytics service and API endpoints:
- get_usage_summary aggregation
- Course AI usage endpoint
- Platform (system) AI usage endpoint
"""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from core.models import AIUsageRecord
from core.services.ai_usage_analytics import get_usage_summary
from core.tests.utils import request_as, setUpBase
from core.tests.views.personas import Persona
from core.tests.factories import CourseFactory, OrganizationFactory


# ===========================================================================
# Service-level tests for get_usage_summary
# ===========================================================================

class TestGetUsageSummary(APITestCase):
    """Test the get_usage_summary analytics service function."""

    def setUp(self):
        setUpBase(self)
        self.org = self.DB['Organization']
        self.course = self.DB['Course']
        self.assignment = self.DB['Assignment']
        self.user = self.course.courseAdmins.first()
        self.now = timezone.now()

        # Create some usage records
        for i in range(5):
            AIUsageRecord.objects.create(
                organization=self.org,
                course=self.course,
                assignment=self.assignment,
                user=self.user,
                provider='openai',
                model='gpt-4o-mini',
                request_type='comment_generation',
                input_tokens=1000 * (i + 1),
                output_tokens=200 * (i + 1),
                total_tokens=1200 * (i + 1),
                estimated_cost=Decimal('0.001') * (i + 1),
                status='success',
            )

    def test_summary_totals(self):
        summary = get_usage_summary(
            queryset=AIUsageRecord.objects.filter(course=self.course),
            granularity='daily',
        )
        # Sum of 1+2+3+4+5 = 15, ×1000 = 15000 input, ×200 = 3000 output
        self.assertEqual(summary['totalTokens'], 18000)  # 15000 + 3000
        self.assertEqual(summary['inputTokens'], 15000)
        self.assertEqual(summary['outputTokens'], 3000)
        self.assertEqual(summary['requestCount'], 5)

    def test_summary_time_series(self):
        summary = get_usage_summary(
            queryset=AIUsageRecord.objects.filter(course=self.course),
            granularity='daily',
        )
        # All created "now" → should appear in a single daily bucket
        self.assertGreaterEqual(len(summary['timeSeries']), 1)
        bucket = summary['timeSeries'][0]
        self.assertIn('totalTokens', bucket)
        self.assertIn('requestCount', bucket)
        self.assertEqual(bucket['requestCount'], 5)

    def test_summary_breakdown_by_course(self):
        summary = get_usage_summary(
            queryset=AIUsageRecord.objects.filter(organization=self.org),
            granularity='daily',
            breakdown_field='course',
            breakdown_name_field='course__name',
        )
        self.assertGreaterEqual(len(summary['breakdown']), 1)
        item = summary['breakdown'][0]
        self.assertIn('id', item)
        self.assertIn('name', item)
        self.assertEqual(item['id'], self.course.id)

    def test_summary_no_records(self):
        """Returns zeros when there are no records."""
        summary = get_usage_summary(
            queryset=AIUsageRecord.objects.none(),
            granularity='daily',
        )
        self.assertEqual(summary['totalTokens'], 0)
        self.assertEqual(summary['requestCount'], 0)
        self.assertEqual(summary['timeSeries'], [])

    def test_summary_granularity_hourly(self):
        summary = get_usage_summary(
            queryset=AIUsageRecord.objects.filter(course=self.course),
            granularity='hourly',
        )
        self.assertEqual(summary['granularity'], 'hourly')
        self.assertEqual(summary['requestCount'], 5)

    def test_summary_granularity_monthly(self):
        summary = get_usage_summary(
            queryset=AIUsageRecord.objects.filter(course=self.course),
            granularity='monthly',
        )
        self.assertEqual(summary['granularity'], 'monthly')
        self.assertEqual(summary['requestCount'], 5)

    def test_summary_date_filtering(self):
        """Records outside the date range are excluded."""
        future = self.now + timedelta(days=100)
        summary = get_usage_summary(
            queryset=AIUsageRecord.objects.filter(course=self.course),
            granularity='daily',
            start_date=future,
            end_date=future + timedelta(days=1),
        )
        self.assertEqual(summary['requestCount'], 0)


# ===========================================================================
# Course AI Usage endpoint
# ===========================================================================

class TestCourseAIUsageEndpoint(APITestCase):
    """Test GET /courses/{id}/aiUsage/"""

    def setUp(self):
        setUpBase(self)
        self.course = self.DB['Course']
        self.org = self.DB['Organization']
        self.endpoint = reverse('course-aiUsage', args=[self.course.id])

        # Create some records
        user = self.course.courseAdmins.first()
        for _ in range(3):
            AIUsageRecord.objects.create(
                organization=self.org,
                course=self.course,
                assignment=self.DB['Assignment'],
                user=user,
                provider='openai',
                model='gpt-4o-mini',
                request_type='comment_generation',
                input_tokens=500,
                output_tokens=100,
                total_tokens=600,
                estimated_cost=Decimal('0.0001'),
                status='success',
            )

    def test_students_cannot_access(self):
        student = Persona.STUDENT_OF_COURSE(self)
        response = request_as('read', student, self.endpoint, {})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_graders_cannot_access(self):
        grader = Persona.GRADER_OF_COURSE(self)
        response = request_as('read', grader, self.endpoint, {})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_access(self):
        admin = Persona.ADMIN_OF_COURSE(self)
        response = request_as('read', admin, self.endpoint, {})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_returns_expected_shape(self):
        admin = Persona.ADMIN_OF_COURSE(self)
        response = request_as('read', admin, self.endpoint, {})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.data
        self.assertIn('totalTokens', data)
        self.assertIn('inputTokens', data)
        self.assertIn('outputTokens', data)
        self.assertIn('estimatedCost', data)
        self.assertIn('requestCount', data)
        self.assertIn('timeSeries', data)
        self.assertIn('breakdown', data)
        self.assertIn('granularity', data)

        self.assertEqual(data['requestCount'], 3)
        self.assertEqual(data['totalTokens'], 1800)

    def test_granularity_query_param(self):
        admin = Persona.ADMIN_OF_COURSE(self)
        from rest_framework.test import APIClient
        client = APIClient()
        client.force_authenticate(user=admin)
        response = client.get(self.endpoint + '?granularity=hourly')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['granularity'], 'hourly')

    def test_other_course_admin_cannot_access(self):
        """Admin of a different course in the same org cannot view usage."""
        other_admin = Persona.ADMIN_OF_OTHER_COURSE(self)
        response = request_as('read', other_admin, self.endpoint, {})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


# ===========================================================================
# Organization AI Usage endpoint
# ===========================================================================

class TestOrganizationAIUsageEndpoint(APITestCase):
    """Test GET /organizations/{id}/aiUsage/"""

    def setUp(self):
        setUpBase(self)
        self.org = self.DB['Organization']
        self.course = self.DB['Course']
        self.endpoint = reverse('organization-aiUsage', args=[self.org.id])

        user = self.course.courseAdmins.first()
        for _ in range(4):
            AIUsageRecord.objects.create(
                organization=self.org,
                course=self.course,
                assignment=self.DB['Assignment'],
                user=user,
                provider='gemini',
                model='gemini-2.5-flash',
                request_type='comment_generation',
                input_tokens=800,
                output_tokens=300,
                total_tokens=1100,
                estimated_cost=Decimal('0.0002'),
                status='success',
            )

    def test_non_staff_forbidden(self):
        grader = Persona.GRADER_OF_COURSE(self)
        response = request_as('read', grader, self.endpoint, {})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_superuser_can_access(self):
        su = User.objects.create_superuser('su_usage@test.edu', 'su_usage@test.edu', 'pass')
        response = request_as('read', su, self.endpoint, {})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['requestCount'], 4)
        self.assertEqual(response.data['totalTokens'], 4400)

    def test_breakdown_by_course(self):
        su = User.objects.create_superuser('su_bd@test.edu', 'su_bd@test.edu', 'pass')
        response = request_as('read', su, self.endpoint, {})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Breakdown should be by course
        self.assertGreaterEqual(len(response.data['breakdown']), 1)
        self.assertEqual(response.data['breakdown'][0]['id'], self.course.id)


# ===========================================================================
# Platform (System) AI Usage endpoint
# ===========================================================================

class TestSystemAIUsageEndpoint(APITestCase):
    """Test GET /system/aiUsage/"""

    def setUp(self):
        setUpBase(self)
        self.org = self.DB['Organization']
        self.course = self.DB['Course']
        self.other_org = self.DB['Other_Org_Course'].organization
        self.endpoint = reverse('system_ai_usage')

        user = self.course.courseAdmins.first()
        # Records for org 1
        for _ in range(3):
            AIUsageRecord.objects.create(
                organization=self.org,
                course=self.course,
                user=user,
                provider='openai',
                model='gpt-4o-mini',
                request_type='comment_generation',
                input_tokens=1000,
                output_tokens=200,
                total_tokens=1200,
                estimated_cost=Decimal('0.0003'),
                status='success',
            )
        # Records for org 2
        other_user = self.DB['Other_Org_Course'].courseAdmins.first()
        for _ in range(2):
            AIUsageRecord.objects.create(
                organization=self.other_org,
                course=self.DB['Other_Org_Course'],
                user=other_user,
                provider='gemini',
                model='gemini-2.5-flash',
                request_type='test_generation',
                input_tokens=500,
                output_tokens=100,
                total_tokens=600,
                estimated_cost=Decimal('0.0001'),
                status='success',
            )

    def test_non_staff_is_forbidden(self):
        """Regular users cannot access platform usage."""
        admin = Persona.ADMIN_OF_COURSE(self)
        response = request_as('read', admin, self.endpoint, {})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_superuser_can_access(self):
        su = User.objects.create_superuser('su_sys@test.edu', 'su_sys@test.edu', 'pass')
        response = request_as('read', su, self.endpoint, {})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # All 5 records across both orgs
        self.assertEqual(response.data['requestCount'], 5)

    def test_platform_shows_all_orgs(self):
        su = User.objects.create_superuser('su_all@test.edu', 'su_all@test.edu', 'pass')
        response = request_as('read', su, self.endpoint, {})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Breakdown should include both orgs
        org_ids = {item['id'] for item in response.data['breakdown']}
        self.assertIn(self.org.id, org_ids)
        self.assertIn(self.other_org.id, org_ids)

    def test_filter_by_organization_id(self):
        su = User.objects.create_superuser('su_filter@test.edu', 'su_filter@test.edu', 'pass')
        from rest_framework.test import APIClient
        client = APIClient()
        client.force_authenticate(user=su)
        response = client.get(self.endpoint + f'?organizationId={self.org.id}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Only org1 records (3 of them)
        self.assertEqual(response.data['requestCount'], 3)

    def test_filter_by_other_org(self):
        su = User.objects.create_superuser('su_filter2@test.edu', 'su_filter2@test.edu', 'pass')
        from rest_framework.test import APIClient
        client = APIClient()
        client.force_authenticate(user=su)
        response = client.get(self.endpoint + f'?organizationId={self.other_org.id}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['requestCount'], 2)

    def test_response_shape(self):
        su = User.objects.create_superuser('su_shape@test.edu', 'su_shape@test.edu', 'pass')
        response = request_as('read', su, self.endpoint, {})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.data
        expected_keys = {
            'totalTokens', 'inputTokens', 'outputTokens', 'estimatedCost',
            'requestCount', 'timeSeries', 'breakdown', 'modelBreakdown',
            'granularity', 'startDate', 'endDate',
        }
        self.assertEqual(set(data.keys()), expected_keys)

    def test_staff_user_can_access(self):
        """is_staff (non-superuser) should also be able to access."""
        staff = User.objects.create_user('staff@test.edu', 'staff@test.edu', 'pass', is_staff=True)
        response = request_as('read', staff, self.endpoint, {})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
