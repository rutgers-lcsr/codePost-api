# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.

# Install pkg_resources shim for setuptools >= 82 compatibility
from core.compat import install_pkg_resources_shim
install_pkg_resources_shim()

from autograder.celery import app as celery_app
__all__ = ['celery_app']
