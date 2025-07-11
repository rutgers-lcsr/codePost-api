from rest_framework import permissions


class TemplatePermission(permissions.BasePermission):

  def has_permission(self, request, view):
    if request.method == "POST":
      serializer = view.get_serializer(data=request.data)
      if serializer.is_valid(raise_exception=False):
        obj = serializer.createForPOSTCheck()
        return self.has_object_permission(request, view, obj)

    return True


class SuperuserPermission(permissions.BasePermission):

  def has_permission(self, request, view):
    return request.user.is_superuser
