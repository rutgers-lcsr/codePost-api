# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from core.tests.views.permissions_base import BaseTestCases, initPermissionsClass


class TestPermissions_Organization_Base(BaseTestCases.TestPermissions):

  def __init__(self, *args, **kwargs):
    initPermissionsClass(self)
    super().__init__(*args, model=self.model, permissions=self.permissions, **kwargs)
