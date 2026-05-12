# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from rest_framework import viewsets

from django.shortcuts import redirect
from django.urls import reverse


class FileTemplateViewSet(viewsets.ViewSet):
  """
  Deprecated - redirects to AssignmentFile endpoint.
  """
  
  def list(self, request):
    return redirect(reverse('assignmentfile-list'), permanent=True)
  
  def create(self, request):
    return redirect(reverse('assignmentfile-list'), permanent=True)
  
  def retrieve(self, request, pk=None):
    # Redirect to assignmentfile detail if pk is provided
    return redirect(reverse('assignmentfile-detail', args=[pk]), permanent=True)
  
  def update(self, request, pk=None):
    return redirect(reverse('assignmentfile-detail', args=[pk]), permanent=True)
  
  def partial_update(self, request, pk=None):
    return redirect(reverse('assignmentfile-detail', args=[pk]), permanent=True)
  
  def destroy(self, request, pk=None):
    return redirect(reverse('assignmentfile-detail', args=[pk]), permanent=True)


# class FileTemplateViewSet(ListProtectedViewSet):
#   """
#   list:
#   Return a list of all the file templates.

#   create:
#   Create a new file template.

#   retrieve:
#   Return the given file template.

#   update:
#   Update a file template.

#   partial_update:
#   Update a file template.

#   delete:
#   Delete a file template.
#   """
#   queryset = FileTemplate.objects.all()
#   serializer_class = FileTemplateSerializer
#   permission_classes = (IsAuthenticated, FileTemplatePermissions)
