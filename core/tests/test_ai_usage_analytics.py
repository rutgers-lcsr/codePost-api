# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
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

    def test_end_date_at_midnight_is_inclusive(self):
        """An end_date at 00:00:00 (bare date) should still include records created that day."""
        # Create a record at 14:00 on a specific day
        specific_day = self.now.replace(hour=14, minute=30, second=0, microsecond=0)
        AIUsageRecord.objects.create(
            organization=self.org,
            course=self.course,
            assignment=self.assignment,
            user=self.user,
            provider='openai',
            model='gpt-4o-mini',
            request_type='comment_generation',
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
            estimated_cost=Decimal('0.001'),
            status='success',
        )
        # Manually set the created timestamp to the specific time
        record = AIUsageRecord.objects.latest('id')
        AIUsageRecord.objects.filter(pk=record.pk).update(created=specific_day)

        # Query with end_date at midnight of the same day (simulating a date picker)
        midnight = specific_day.replace(hour=0, minute=0, second=0, microsecond=0)
        summary = get_usage_summary(
            queryset=AIUsageRecord.objects.filter(pk=record.pk),
            granularity='daily',
            start_date=midnight,
            end_date=midnight,  # same day at 00:00:00 — should be snapped to end-of-day
        )
        self.assertEqual(summary['requestCount'], 1)


class TestProjectedCost(APITestCase):
    """Test read-time cost projection (token sums x current rates)."""

    def setUp(self):
        setUpBase(self)
        self.org = self.DB['Organization']
        self.course = self.DB['Course']
        self.assignment = self.DB['Assignment']
        self.user = self.course.courseAdmins.first()

        # Historical records frozen at $0 (rates were not configured yet)
        for _ in range(2):
            AIUsageRecord.objects.create(
                organization=self.org,
                course=self.course,
                assignment=self.assignment,
                user=self.user,
                provider='portkey',
                model='proj-model',
                request_type='comment_generation',
                input_tokens=1_000_000,
                output_tokens=500_000,
                total_tokens=1_500_000,
                estimated_cost=Decimal('0'),
                status='success',
            )
        self.queryset = AIUsageRecord.objects.filter(course=self.course, model='proj-model')

    def test_projected_cost_with_custom_rates(self):
        summary = get_usage_summary(
            queryset=self.queryset,
            granularity='daily',
            breakdown_field='assignment',
            breakdown_name_field='assignment__name',
            projection_rates={'proj-model': {'input': 1.0, 'output': 2.0}},
        )
        # 2M input x $1/M + 1M output x $2/M = $4; stored cost stays 0
        self.assertEqual(Decimal(summary['estimatedCost']), Decimal('0'))
        self.assertEqual(Decimal(summary['projectedCost']), Decimal('4'))
        self.assertEqual(Decimal(summary['timeSeries'][0]['projectedCost']), Decimal('4'))
        self.assertEqual(Decimal(summary['breakdown'][0]['projectedCost']), Decimal('4'))
        self.assertEqual(Decimal(summary['modelBreakdown'][0]['projectedCost']), Decimal('4'))
        self.assertEqual(Decimal(summary['featureBreakdown'][0]['projectedCost']), Decimal('4'))

    def test_projected_cost_falls_back_to_default_rates(self):
        # gpt-4o-mini is in TOKEN_RATES; no projection_rates passed
        AIUsageRecord.objects.create(
            organization=self.org, course=self.course, user=self.user,
            provider='openai', model='gpt-4o-mini',
            request_type='comment_generation',
            input_tokens=1_000_000, output_tokens=1_000_000, total_tokens=2_000_000,
            estimated_cost=Decimal('0'), status='success',
        )
        summary = get_usage_summary(
            queryset=AIUsageRecord.objects.filter(course=self.course, model='gpt-4o-mini'),
            granularity='daily',
        )
        self.assertEqual(Decimal(summary['projectedCost']), Decimal('0.75'))

    def test_projected_cost_unknown_model_is_zero(self):
        summary = get_usage_summary(queryset=self.queryset, granularity='daily')
        self.assertEqual(Decimal(summary['projectedCost']), Decimal('0'))

    def test_projected_cost_applies_cached_token_discount(self):
        AIUsageRecord.objects.create(
            organization=self.org, course=self.course, user=self.user,
            provider='gemini', model='gemini-2.5-flash',
            request_type='comment_generation',
            input_tokens=1_000_000, output_tokens=0, total_tokens=1_000_000,
            cached_tokens=1_000_000,
            estimated_cost=Decimal('0'), status='success',
        )
        summary = get_usage_summary(
            queryset=AIUsageRecord.objects.filter(course=self.course, model='gemini-2.5-flash'),
            granularity='daily',
        )
        # All input cached: 1M x $0.15/M x 25% = $0.0375
        self.assertEqual(Decimal(summary['projectedCost']), Decimal('0.0375'))


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

    def test_projected_cost_uses_course_rate_over_org(self):
        """Course token-rate override beats the org rate in the projection."""
        self.org.ai_token_rates = {'gpt-4o-mini': {'input': 10.0, 'output': 10.0}}
        self.org.save()
        self.course.ai_token_rates = {'gpt-4o-mini': {'input': 100.0, 'output': 100.0}}
        self.course.save()

        admin = Persona.ADMIN_OF_COURSE(self)
        response = request_as('read', admin, self.endpoint, {})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # 1500 input + 300 output tokens at $100/M each = $0.18
        self.assertEqual(Decimal(response.data['projectedCost']), Decimal('0.18'))


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
            'totalTokens', 'inputTokens', 'outputTokens', 'cachedTokens',
            'estimatedCost', 'projectedCost', 'requestCount', 'timeSeries', 'breakdown',
            'modelBreakdown', 'featureBreakdown', 'granularity', 'startDate', 'endDate',
        }
        self.assertEqual(set(data.keys()), expected_keys)

    def test_feature_breakdown_uses_display_labels(self):
        su = User.objects.create_superuser('su_feat@test.edu', 'su_feat@test.edu', 'pass')
        response = request_as('read', su, self.endpoint, {})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = [entry['name'] for entry in response.data['featureBreakdown']]
        self.assertTrue(names)
        # Labels come from REQUEST_TYPE_CHOICES, not raw keys
        self.assertNotIn('comment_generation', names)

    def test_staff_user_can_access(self):
        """is_staff (non-superuser) should also be able to access."""
        staff = User.objects.create_user('staff@test.edu', 'staff@test.edu', 'pass', is_staff=True)
        response = request_as('read', staff, self.endpoint, {})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_projected_cost_uses_each_orgs_own_rates(self):
        """Platform projection resolves each organization's ai_token_rates."""
        self.org.ai_token_rates = {'gpt-4o-mini': {'input': 10.0, 'output': 10.0}}
        self.org.save()
        self.other_org.ai_token_rates = {'gemini-2.5-flash': {'input': 100.0, 'output': 100.0}}
        self.other_org.save()

        su = User.objects.create_superuser('su_proj@test.edu', 'su_proj@test.edu', 'pass')
        response = request_as('read', su, self.endpoint, {})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        projections = {item['id']: Decimal(item['projectedCost']) for item in response.data['breakdown']}
        # Org 1: 3000 input + 600 output tokens at $10/M = $0.036
        self.assertEqual(projections[self.org.id], Decimal('0.036'))
        # Org 2: 1000 input + 200 output tokens at $100/M = $0.12
        self.assertEqual(projections[self.other_org.id], Decimal('0.12'))
        self.assertEqual(Decimal(response.data['projectedCost']), Decimal('0.156'))
