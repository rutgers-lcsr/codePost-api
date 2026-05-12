# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from django.urls import path
from core.views.auth import current_user

import core.views.registration as registration

urlpatterns = [
    path('current_user/', current_user),

    # Join Flow
    path('emailRegistration/', registration.emailRegistration),
    path('verifyRegistrationToken/', registration.verifyRegistrationToken),
    path('registerAndSetPassword/', registration.registerAndSetPassword),

    # Create Flow
    path('validateNewAdminUser/', registration.validateNewAdminUser),
    path('handleValidationResponse/', registration.handleValidationResponse),
    path('checkStatusNewAdminUser/', registration.checkStatusNewAdminUser),

    # Password Reset
    path('emailPasswordReset/', registration.emailPasswordReset),
    path('verifyResetToken/', registration.verifyResetToken),
    path('resetPassword/', registration.resetPassword),

    path('setCredentials/', registration.setCredentials),
    path('graderToAdmin/', registration.graderToAdmin),
]
