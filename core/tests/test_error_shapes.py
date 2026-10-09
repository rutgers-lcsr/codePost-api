# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""
Errors reach the client as JSON with a `detail` string, never as Django's HTML
pages — and user input that used to crash a view (500) is now a readable 4xx.
"""
import base64
import json

from django.core.exceptions import ObjectDoesNotExist, ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.http import HttpResponse, JsonResponse
from django.test import RequestFactory, SimpleTestCase
from rest_framework import status
from rest_framework.test import APITestCase

from core.exceptions import exception_handler
from core.middleware import ErrorBodyShapeMiddleware
from core.tests.factories import OrganizationFactory, UserFactory


class TestExceptionHandler(SimpleTestCase):
    def _handle(self, exc):
        return exception_handler(exc, {'request': None})

    def test_model_validation_error_is_400_with_detail(self):
        resp = self._handle(DjangoValidationError("content does not match the claimed MIME type"))
        self.assertEqual(resp.status_code, 400)
        self.assertIn('MIME', resp.data['detail'])

    def test_field_keyed_validation_error_keeps_field_errors(self):
        resp = self._handle(DjangoValidationError({'name': ['Too long.'], 'period': ['Required.']}))
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data['name'], ['Too long.'])
        self.assertEqual(resp.data['detail'], 'Too long.')

    def test_integrity_error_is_409(self):
        resp = self._handle(IntegrityError("UNIQUE constraint failed"))
        self.assertEqual(resp.status_code, 409)
        self.assertIn('already in use', resp.data['detail'])

    def test_does_not_exist_is_404(self):
        resp = self._handle(ObjectDoesNotExist())
        self.assertEqual(resp.status_code, 404)
        self.assertIn('could not be found', resp.data['detail'])

    def test_unknown_exception_is_left_to_django(self):
        self.assertIsNone(self._handle(RuntimeError("boom")))


class TestErrorBodyShapeMiddleware(SimpleTestCase):
    def _run(self, response):
        mw = ErrorBodyShapeMiddleware(lambda request: response)
        return json.loads(mw(RequestFactory().get('/x/')).content)

    def test_bare_string_becomes_detail(self):
        self.assertEqual(self._run(JsonResponse("Nope", status=403, safe=False)), {'detail': 'Nope'})

    def test_error_key_gains_detail_and_keeps_error(self):
        body = self._run(JsonResponse({'error': 'AI is not configured.'}, status=400))
        self.assertEqual(body, {'error': 'AI is not configured.', 'detail': 'AI is not configured.'})

    def test_code_plus_message_uses_message(self):
        body = self._run(JsonResponse({'error': 'in_use', 'message': 'This bank is in use.'}, status=409))
        self.assertEqual(body['detail'], 'This bank is in use.')

    def test_list_of_strings_becomes_detail(self):
        body = self._run(JsonResponse(["Late submissions are not allowed."], status=400, safe=False))
        self.assertEqual(body['detail'], "Late submissions are not allowed.")
        self.assertEqual(body['nonFieldErrors'], ["Late submissions are not allowed."])

    def test_form_errors_dict_gets_first_message(self):
        body = self._run(JsonResponse({'errors': {'email': ['Enter a valid email.']}}, status=400))
        self.assertEqual(body['detail'], 'Enter a valid email.')

    def test_field_errors_and_existing_detail_untouched(self):
        self.assertEqual(self._run(JsonResponse({'name': ['Required.']}, status=400)), {'name': ['Required.']})
        self.assertEqual(self._run(JsonResponse({'detail': 'x'}, status=400)), {'detail': 'x'})

    def test_success_and_non_json_untouched(self):
        mw = ErrorBodyShapeMiddleware(lambda request: HttpResponse("<h1>nope</h1>", status=500))
        self.assertEqual(mw(RequestFactory().get('/x/')).content, b"<h1>nope</h1>")
        mw = ErrorBodyShapeMiddleware(lambda request: JsonResponse("fine", status=200, safe=False))
        self.assertEqual(json.loads(mw(RequestFactory().get('/x/')).content), "fine")


class TestEndpointErrorShapes(APITestCase):
    def setUp(self):
        org = OrganizationFactory(name="ErrOrg", shortname="EO")
        self.admin = UserFactory(username="admin@eo.edu", email="admin@eo.edu")
        self.admin.profile.organization = org
        self.admin.profile.canCreateCourses = True
        self.admin.profile.canModifyRosters = True
        self.admin.save()
        self.student = UserFactory(username="student@eo.edu", email="student@eo.edu")
        self.student.profile.organization = org
        self.student.save()

        self.client.force_authenticate(user=self.admin)
        self.course_id = self.client.post('/courses/', {"name": "CS Err", "period": "F2026"}).data['id']
        self.client.patch(f'/courses/{self.course_id}/roster/', {"students": [self.student.email]})
        self.assignment_id = self.client.post('/assignments/', {
            "name": "HW", "points": 10, "state": "published", "allowStudentUpload": True,
            "course": self.course_id, "allowStudentUploadWithPartners": True,
        }).data['id']

    def _upload(self, files):
        self.client.force_authenticate(user=self.student)
        return self.client.post(f'/assignments/{self.assignment_id}/studentUpload/',
                                {"files": files, "sendConfirmationEmail": False}, format='json')

    # --- studentUpload: former 500s ----------------------------------------

    def test_mislabelled_data_uri_is_400_and_keeps_old_files(self):
        first = self._upload([{"name": "a.txt", "data": "hello", "extension": ".txt", "path": ""}])
        self.assertEqual(first.status_code, 200, first.data)

        fake_pdf = 'data:application/pdf;base64,' + base64.b64encode(b'not a pdf').decode()
        resp = self._upload([{"name": "r.pdf", "data": fake_pdf, "extension": ".pdf", "path": ""}])
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.content[:200])
        self.assertEqual(resp.data['file'], 'r.pdf')
        self.assertIn('MIME', str(resp.data))

        # The failed replace must not have deleted the previous submission's files.
        self.client.force_authenticate(user=self.admin)
        sub = self.client.get(f'/assignments/{self.assignment_id}/submissions/').data[0]
        self.assertEqual([f['name'] for f in self.client.get(f"/submissions/{sub['id']}/").data['files']], ['a.txt'])

    def test_missing_optional_path_is_accepted(self):
        resp = self._upload([{"name": "a.txt", "data": "x", "extension": ".txt"}])
        self.assertEqual(resp.status_code, 200, resp.data)

    def test_files_not_a_list_is_400(self):
        resp = self._upload("a.txt")
        self.assertEqual(resp.status_code, 400)
        resp = self._upload([{"data": "x", "extension": ".txt"}])  # no name
        self.assertEqual(resp.status_code, 400)
        self.assertIn('name', resp.data)

    # --- lookups that used to raise DoesNotExist --------------------------

    def test_unknown_submission_is_json_404(self):
        self.client.force_authenticate(user=self.admin)
        for path in ('/submissions/999999/history/', '/submissions/999999/testResults/',
                     '/submissions/999999/validatePartnerLink/?token=x'):
            resp = self.client.get(path)
            self.assertEqual(resp.status_code, 404, path)
            self.assertEqual(resp['Content-Type'].split(';')[0], 'application/json', path)
            self.assertIn('detail', resp.json(), path)

    def test_unknown_route_is_json_404(self):
        resp = self.client.get('/no/such/route/')
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp['Content-Type'].split(';')[0], 'application/json')
        self.assertIn('/no/such/route/', resp.json()['detail'])

    # --- helper bodies and reasons ---------------------------------------

    def test_partner_link_refusals_say_why(self):
        self.client.force_authenticate(user=self.student)
        sub_id = self._upload([{"name": "a.txt", "data": "x", "extension": ".txt", "path": ""}]).data['id']
        resp = self.client.get(f'/submissions/{sub_id}/validatePartnerLink/')
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()['detail'], 'A partner link token is required.')

    def test_regrade_without_text_is_400_not_500(self):
        self.client.force_authenticate(user=self.student)
        sub_id = self._upload([{"name": "a.txt", "data": "x", "extension": ".txt", "path": ""}]).data['id']
        resp = self.client.patch(f'/submissions/{sub_id}/submitRegrade/', {}, format='json')
        self.assertIn(resp.status_code, (400, 403))
        self.assertIn('detail', resp.json())

    def test_forbidden_helper_body_has_detail(self):
        # /users/{email}/email/ answers an unknown course with returnForbidden() — the
        # bare-string helper that now returns {'detail': ...}.
        self.client.force_authenticate(user=self.admin)
        resp = self.client.post(f'/users/{self.student.email}/email/', {"course": 999999}, format='json')
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()['detail'], 'You do not have permission to perform this action.')
