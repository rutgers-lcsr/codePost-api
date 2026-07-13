# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from typing import TYPE_CHECKING
from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework.request import Request

from core.permissions.helpers import returnNotAuthorized, returnForbidden
from core.permissions.helpers import isAuthenticated

from rest_framework.pagination import PageNumberPagination


class ListPagination(PageNumberPagination):
  page_size = 50
  page_size_query_param = 'page_size'


class ListProtectedViewSet(viewsets.ModelViewSet):
  if TYPE_CHECKING:
    request: Request

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

      # Use the viewset's pagination_class if one is set (e.g. UserViewSet).
      # ViewSets without pagination_class (e.g. OrganizationViewSet,
      # CourseViewSet) return all results as a plain array, which keeps the
      # OpenAPI schema in sync with the actual response format.
      page = self.paginate_queryset(queryset)
      if page is not None:
        serializer = self.get_serializer(page, many=True)
        return self.get_paginated_response(serializer.data)

      serializer = self.get_serializer(queryset, many=True)
      return Response(serializer.data)
    else:
      return super().list(request)
