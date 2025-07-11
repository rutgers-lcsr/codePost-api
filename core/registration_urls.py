from django.urls import path, re_path, include
from django.views.generic import TemplateView
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
    path('validateMoocSignup/', registration.validateMoocSignup),
    path('handleValidationResponse/', registration.handleValidationResponse),
    path('checkStatusNewAdminUser/', registration.checkStatusNewAdminUser),

    # Password Reset
    path('emailPasswordReset/', registration.emailPasswordReset),
    path('verifyResetToken/', registration.verifyResetToken),
    path('resetPassword/', registration.resetPassword),

    path('setCredentials/', registration.setCredentials),
    path('graderToAdmin/', registration.graderToAdmin),
]
