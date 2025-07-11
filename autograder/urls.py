from django.urls import path, re_path, include


from autograder.views.environment import EnvironmentViewSet
from autograder.views.sourceFile import SourceFileViewSet
from autograder.views.solutionFile import SolutionFileViewSet
from autograder.views.helperFile import HelperFileViewSet
from autograder.views.TaskViewset import TaskViewSet

from rest_framework import routers

router = routers.DefaultRouter()
router.register(r"environments", EnvironmentViewSet)
router.register(r"sourceFiles", SourceFileViewSet)
router.register(r"solutionFiles", SolutionFileViewSet)
router.register(r"helperFiles", HelperFileViewSet)

urlpatterns = [
    path(r"tasks/<str:pk>/", TaskViewSet.as_view({"get": "retrieve"})),
    re_path("", include(router.urls)),
]
