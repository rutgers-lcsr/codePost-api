from django.http import HttpResponse
from django.urls import path, re_path, include


from autograder.views.environment import EnvironmentViewSet
from autograder.views.sourceFile import SourceFileViewSet
from autograder.views.solutionFile import SolutionFileViewSet
from autograder.views.helperFile import HelperFileViewSet
from autograder.views.TaskViewset import TaskViewSet
from autograder.views.executor import (
    ExecuteFileView,
)
from autograder.views.executor_streaming import ExecuteFileStreaming
from autograder.views.cache_check import CheckExecutionCache

from rest_framework import routers
def health_check(request):
    return HttpResponse(status=200)
router = routers.DefaultRouter()
router.register(r"environments", EnvironmentViewSet)
router.register(r"sourceFiles", SourceFileViewSet)
router.register(r"solutionFiles", SolutionFileViewSet)
router.register(r"helperFiles", HelperFileViewSet)


urlpatterns = [
    path(r"tasks/<str:pk>/", TaskViewSet.as_view({"get": "retrieve"})),
    path(r"execute/file/", ExecuteFileView.as_view(), name="execute-file"),
    path(r"execute/file/streaming/", ExecuteFileStreaming.as_view(), name="execute-file-streaming"),
    path(r"execute/file/cache/check/", CheckExecutionCache.as_view(), name="check-execution-cache"),
    path("health/", health_check, name="health-check"),
    re_path("", include(router.urls)),
]
