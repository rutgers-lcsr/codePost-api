# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from django.contrib.auth.models import User
from core.models import Organization

# Create superuser
james = User.objects.create(username="james@example.com", email="james@example.com")
princeton = Organization.objects.create(name="Princeton University", shortname="Princeton")
james.is_superuser = True
james.set_password('rootabega')
james.is_staff = True
james.save()

james.profile.organization = princeton
james.profile.canCreateCourses = True
james.profile.canModifyRosters = True

james.save()