from rest_framework import viewsets
from rest_framework.response import Response

from core.permissions.helpers import returnNotAuthorized, returnForbidden, returnNotFound
from core.permissions.helpers import isAuthenticated
from core.permissions.helpers import isStudent, isGrader, isCourseAdmin, isCourseMember
from core.permissions.helpers import isStudentOfSub, isStaffOfSub

from rest_framework.pagination import PageNumberPagination


class ListPagination(PageNumberPagination):
  page_size = 50
  page_size_query_param = 'page_size'


class ListProtectedViewSet(viewsets.ModelViewSet):

  def list(self, request):
    user = request.user

    if not isAuthenticated(user):
      return returnNotAuthorized()

    return returnForbidden()


class SuperUserListProtectedViewSet(ListProtectedViewSet):

  def list(self, request):
    user = request.user

    # mixins.ListModelMixin
    if user.is_superuser:
      queryset = self.filter_queryset(self.get_queryset())
      paginator = ListPagination()
      page = paginator.paginate_queryset(queryset, request)
      if page is not None:
        serializer = self.get_serializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

      # Should never get here
      return returnNotAuthorized()
    else:
      return super().list(request)
