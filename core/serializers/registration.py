# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from rest_framework import serializers


class EmailRegistrationRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()
    token = serializers.CharField(help_text='Invite code for the course')


class EmailRegistrationResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    code_valid = serializers.BooleanField()
    email_valid = serializers.BooleanField()


class VerifyRegistrationTokenRequestSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()


class VerifyRegistrationTokenResponseSerializer(serializers.Serializer):
    isValid = serializers.BooleanField()
    email = serializers.EmailField(required=False)


class RegisterAndSetPasswordRequestSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    password1 = serializers.CharField()
    password2 = serializers.CharField()


class RegisterAndSetPasswordResponseSerializer(serializers.Serializer):
    isValid = serializers.BooleanField()


class SetCredentialsRequestSerializer(serializers.Serializer):
    organization = serializers.CharField()
    password1 = serializers.CharField()
    password2 = serializers.CharField()


class SetCredentialsResponseSerializer(serializers.Serializer):
    isValid = serializers.BooleanField()


class EmptyResponseSerializer(serializers.Serializer):
    pass


class ValidateNewAdminUserRequestSerializer(serializers.Serializer):
    organization = serializers.CharField()
    email = serializers.EmailField()


class ValidateNewAdminUserResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    action_id = serializers.CharField()
    is_new_org = serializers.BooleanField(required=False)
    pending = serializers.BooleanField(required=False)


class HandleValidationResponseSerializer(serializers.Serializer):
    isValid = serializers.BooleanField()


class CheckStatusNewAdminUserResponseSerializer(serializers.Serializer):
    pending = serializers.BooleanField()
    status = serializers.BooleanField()


class EmailPasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class EmailPasswordResetResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()


class VerifyResetTokenRequestSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()


class VerifyResetTokenResponseSerializer(serializers.Serializer):
    isValid = serializers.BooleanField()
    email = serializers.EmailField(required=False)


class ResetPasswordRequestSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    password = serializers.CharField()


class ResetPasswordResponseSerializer(serializers.Serializer):
    isValid = serializers.BooleanField()
    success = serializers.BooleanField()
