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
from core.views.auth import obtain_jwt_token, ImpersonateView

from rest_framework.renderers import JSONOpenAPIRenderer

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
from core.views.fileTemplate import FileTemplateViewSet
from core.views.comment import CommentViewSet
from core.views.submissionTest import SubmissionTestViewSet
from core.views.testCase import TestCaseViewSet
from core.views.testCategory import TestCategoryViewSet

from webhooks.view import WebhookViewSet

from core.views.emailList import subscribeToEmailList
from core.views.tmp import activate_cip


from django.http import HttpResponse


def health_check(request):
    return HttpResponse(status=200)

router = routers.DefaultRouter()
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
router.register(r'fileTemplates', FileTemplateViewSet)
router.register(r'testCases', TestCaseViewSet)
router.register(r'submissionTests', SubmissionTestViewSet)
router.register(r'testCategories', TestCategoryViewSet)
# router.register(r'billing', BillingViewSet, basename='billing')

webhooks_router = routers.DefaultRouter()
webhooks_router.register(r'webhooks', WebhookViewSet)

#############################################
# CoreAPI (built into Django)
# ~/docs/
#############################################

from rest_framework.documentation import include_docs_urls
API_TITLE = 'codePost API'
API_DESCRIPTION = 'An API for administrators to mine course data and automate common tasks.'

#############################################
#############################################

urlpatterns = [
    re_path(r'^docs/', include_docs_urls(title=API_TITLE, description=API_DESCRIPTION,
                                         public=True, renderer_classes=[JSONOpenAPIRenderer])),  # OpenAPI JSON renderer
    # re_path(r'^docs/', include_docs_urls(title=API_TITLE,
    # description=API_DESCRIPTION, public=True,
    # renderer_classes=[CustomRenderer])), # UI renderer
    path('admin/', admin.site.urls),
    re_path('^api-auth/', include('rest_framework.urls', namespace='rest_framework')),
    path('token-auth/', obtain_jwt_token),
    path('token-refresh/', TokenRefreshSlidingView.as_view(), name='token_refresh'),
    path('token-verify/', TokenVerifyView.as_view(), name='token_verify'),
    path('become/', ImpersonateView.as_view(), name='impersonate'),
    re_path('registration/', include(('core.registration_urls', 'core'), namespace='registration')),
    re_path('logs/', include(('core.logging_urls', 'core'), namespace='logging')),
    re_path('autograder/', include(('autograder.urls', 'autograder'), namespace="autograder")),
    re_path('health-check/', health_check),
    path('subscribe/', subscribeToEmailList),
    path('tmp-script/', activate_cip),
    re_path('', include(router.urls)),
    re_path('', include(webhooks_router.urls)),
]
