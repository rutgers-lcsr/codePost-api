# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
"""codepost URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/2.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, re_path, include
from rest_framework import routers
from rest_framework_simplejwt.views import TokenRefreshSlidingView, TokenVerifyView
from core.views.auth import generate_one_time_token, get_jwt_ott, obtain_jwt_token, ImpersonateView, validate_one_time_token, NON_COURSE_KEY_AUTH

from rest_framework.viewsets import ViewSet
from core.views.user import UserViewSet
from core.views.course import CourseViewSet
from core.views.submission import SubmissionViewSet
from core.views.assignment import AssignmentViewSet
from core.views.organization import OrganizationViewSet
from core.views.section import SectionViewSet
from core.views.comment import CommentViewSet
from core.views.rubricCategory import RubricCategoryViewSet
from core.views.rubricComment import RubricCommentViewSet
from core.views.file import FileViewSet
from core.views.submissionFile import SubmissionFileViewSet
from core.views.assignmentFile import AssignmentFileViewSet
from core.views.courseFile import CourseFileViewSet
from core.views.submissionTest import SubmissionTestViewSet
from core.views.testCase import TestCaseViewSet
from core.views.testCategory import TestCategoryViewSet
from core.views.testCategoryResource import TestCategoryResourceViewSet
from core.views.learningObjective import LearningObjectiveViewSet
from core.views.assignmentDataSet import AssignmentDataSetViewSet
from core.views.dashboard import DashboardViewSet
from core.views.commentTemplate import CommentTemplateViewSet
from core.views.suggested_comment import SuggestedCommentViewSet
from core.views.questionBank import QuestionBankViewSet
from core.views.question import QuestionViewSet
from core.views.quiz import QuizViewSet
from core.views.quizQuestion import QuizQuestionViewSet
from core.views.quizQuestionGroup import QuizQuestionGroupViewSet
from core.views.suggestedQuizQuestion import SuggestedQuizQuestionViewSet
from core.views.quizImportJob import QuizImportJobViewSet
from core.views.quizImage import QuizImageViewSet, serve_quiz_image
from core.views.prompt_variant import SystemPromptVariantViewSet
from core.views.prompt_experiment import PromptExperimentViewSet
from core.views.prompt_feedback import PromptFeedbackViewSet
from core.views.prompt_type import PromptTypeListView
from core.views.ai_feature import AIFeatureListView
from core.views.dev_auth import LoginAsRoleView
from codepost.settings import DEBUG

from webhooks.view import WebhookViewSet

from core.views.emailList import subscribeToEmailList
from core.views.tmp import activate_cip
from core.views.system import SystemHealthView, SystemActivityView, SystemBannerView, SystemAIUsageView, SystemAIModelsView
from core.views.capabilities import PlatformCapabilitiesView, BatchCapabilitiesView


from django.http import HttpResponse


def health_check(request):
    return HttpResponse(status=200)

class RedirectToAdminViewSet(ViewSet):
    """
    A simple ViewSet that redirects to the admin interface.
    """
    # This is not a JSON API endpoint; exclude it from OpenAPI generation.
    schema = None

    def list(self, request):
        from django.shortcuts import redirect
        return redirect('/admin/')

router = routers.DefaultRouter()
router.register(r'admin', RedirectToAdminViewSet, basename='admin-redirect')
router.register(r'users', UserViewSet)
router.register(r'courses', CourseViewSet)
router.register(r'submissions', SubmissionViewSet)
router.register(r'assignments', AssignmentViewSet)
router.register(r'organizations', OrganizationViewSet)
router.register(r'sections', SectionViewSet)
router.register(r'comments', CommentViewSet)
router.register(r'rubricCategories', RubricCategoryViewSet)
router.register(r'rubricComments', RubricCommentViewSet)
router.register(r'files', FileViewSet)
router.register(r'submissionFiles', SubmissionFileViewSet)
router.register(r'assignmentFiles', AssignmentFileViewSet)
router.register(r'courseFiles', CourseFileViewSet)
# router.register(r'fileTemplates', AssignmentFileViewSet)  # Deprecated - redirects to AssignmentFileViewSet
router.register(r'testCases', TestCaseViewSet)
router.register(r'testCategories', TestCategoryViewSet)
router.register(r'testCategoryResources', TestCategoryResourceViewSet)
router.register(r'learningObjectives', LearningObjectiveViewSet)
router.register(r'submissionTests', SubmissionTestViewSet)
router.register(r'webhooks', WebhookViewSet)
router.register(r'assignmentDataSets', AssignmentDataSetViewSet)
router.register(r'dashboard', DashboardViewSet, basename='dashboard')
router.register(r'commentTemplates', CommentTemplateViewSet, basename='commentTemplate')
router.register(r'suggestedComments', SuggestedCommentViewSet)
router.register(r'questionBanks', QuestionBankViewSet)
router.register(r'questions', QuestionViewSet)
router.register(r'quizzes', QuizViewSet)
router.register(r'quizQuestions', QuizQuestionViewSet)
router.register(r'quizQuestionGroups', QuizQuestionGroupViewSet)
router.register(r'suggestedQuizQuestions', SuggestedQuizQuestionViewSet)
router.register(r'quizImportJobs', QuizImportJobViewSet)
router.register(r'quizImages', QuizImageViewSet)
router.register(r'promptVariants', SystemPromptVariantViewSet)
router.register(r'promptExperiments', PromptExperimentViewSet)
router.register(r'promptFeedback', PromptFeedbackViewSet)

# router.register(r'billing', BillingViewSet, basename='billing')

#############################################
# API Documentation (drf-spectacular)
# CoreAPI docs removed in Django 6 / DRF 3.15+
# ~/docs/ now redirects to ~/api/schema/swagger-ui/
#############################################

API_TITLE = 'codePost API'
API_DESCRIPTION = 'An API for administrators to mine course data and automate common tasks.'

#############################################
#############################################

urlpatterns = [
    path('admin/', admin.site.urls),
    re_path('^api-auth/', include('rest_framework.urls', namespace='rest_framework')),
    path('token-auth/', obtain_jwt_token),
    path('token-refresh/', TokenRefreshSlidingView.as_view(authentication_classes=NON_COURSE_KEY_AUTH), name='token_refresh'),
    path('token-verify/', TokenVerifyView.as_view(authentication_classes=NON_COURSE_KEY_AUTH), name='token_verify'),
    path('ott/generate/', generate_one_time_token, name='generate_one_time_token'),
    path('ott/validate/', validate_one_time_token, name='validate_one_time_token_by_query'),
    path('ott/', get_jwt_ott, name='get_jwt_ott'),
    re_path('registration/', include(('core.registration_urls', 'core'), namespace='registration')),
    path('auth/sso/', include(('core.sso_urls', 'core'), namespace='sso')),
    re_path('logs/', include(('core.logging_urls', 'core'), namespace='logging')),
    re_path('autograder/', include(('autograder.urls', 'autograder'), namespace="autograder")),
    re_path('health-check/', health_check),
    path('system/health/', SystemHealthView.as_view(), name='system_health'),
    path('system/activity/', SystemActivityView.as_view(), name='system_activity'),
    path('system/banner/', SystemBannerView.as_view(), name='system_banner'),
    path('system/aiUsage/', SystemAIUsageView.as_view(), name='system_ai_usage'),
    path('system/aiModels/', SystemAIModelsView.as_view(), name='system_ai_models'),
    path('subscribe/', subscribeToEmailList),
    path('tmp-script/', activate_cip),
    path('impersonate/', ImpersonateView.as_view(), name='impersonate'),
    path('capabilities/platform/', PlatformCapabilitiesView.as_view(), name='platform_capabilities'),
    path('capabilities/batch/', BatchCapabilitiesView.as_view(), name='batch_capabilities'),
    path('promptTypes/', PromptTypeListView.as_view(), name='prompt_types'),
    path('aiFeatures/', AIFeatureListView.as_view(), name='ai_features'),
    # Public (token-based) serving of quiz description images — must precede the router
    # so it isn't shadowed, and is intentionally unauthenticated (browsers send no auth
    # header on <img> requests; the unguessable token is the access control).
    path('quizImages/raw/<uuid:token>/', serve_quiz_image, name='quiz_image_raw'),
    re_path('', include(router.urls)),
]

if DEBUG:
    # Careful with this endpoint, 
    # you need to run `python manage.py createtestusers` to create the users first
    # and then you can use this endpoint to login as those users, 
    # Make sure to have a course and org set up with assignments, as these users will be added to every
    # course in the database.

    urlpatterns += [
        path('dev-auth/login-as/', LoginAsRoleView.as_view()),
    ]
    
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from django.views.generic import TemplateView, RedirectView

urlpatterns += [
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    # Optional UI:
    path('api/schema/swagger-ui/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/schema/elements/', TemplateView.as_view(template_name='elements.html'), name='elements'),
    # Redirect old /docs/ URL to swagger UI
    path('docs/', RedirectView.as_view(url='/api/schema/swagger-ui/', permanent=True), name='docs-redirect'),
]
