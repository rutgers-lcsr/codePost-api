# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from core.tests.views.permissions_base import BaseTestCases, initPermissionsClass


class TestPermissions_Course_courseSettings_Base(BaseTestCases.TestPermissions):

  def __init__(self, *args, **kwargs):
    initPermissionsClass(self)
    super().__init__(*args, model=self.model, permissions=self.permissions, **kwargs)
