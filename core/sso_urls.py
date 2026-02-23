# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from django.urls import path
from core.views import sso

urlpatterns = [
    path('login/<str:provider>/', sso.initiate_sso, name='sso_login'),
    path('callback/<str:provider>/', sso.sso_callback, name='sso_callback'),
    path('check/', sso.check_sso_availability, name='sso_check'),
]
