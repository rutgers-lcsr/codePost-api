from django import forms
from django.utils.translation import gettext, gettext_lazy as _
from django.contrib.auth import (
    authenticate, get_user_model, password_validation,
)

class PasswordMatchForm(forms.Form):
  error_messages = {
      'password_mismatch': _("The two password fields didn't match."),
  }
  password1 = forms.CharField(
      label=_("Password"),
      strip=False,
      widget=forms.PasswordInput,
      help_text=password_validation.password_validators_help_text_html(),
  )
  password2 = forms.CharField(
      label=_("Password confirmation"),
      widget=forms.PasswordInput,
      strip=False,
      help_text=_("Enter the same password as before, for verification."),
  )

  def clean_password2(self):
      password1 = self.cleaned_data.get("password1")
      password2 = self.cleaned_data.get("password2")
      if password1 and password2 and password1 != password2:
          raise forms.ValidationError(
              self.error_messages['password_mismatch'],
              code='password_mismatch',
          )
      return password2

  def _post_clean(self):
      super()._post_clean()
      # Validate the password after self.instance is updated with form data
      # by super().
      password = self.cleaned_data.get('password2')
      if password:
          try:
              password_validation.validate_password(password)
          except forms.ValidationError as error:
              self.add_error('password2', error)

class ImpersonateForm(forms.Form):
  username = forms.CharField(
      label=_("Username"),
      max_length=150,
      strip=True,
      help_text=_("Enter the username of the user you want to impersonate."),
  )
  never_expire = forms.BooleanField(
      required=False,
      initial=False,
      help_text=_("Check this box if you want the token to never expire."),
  )

class SetCredentialsForm(PasswordMatchForm):
  organization = forms.CharField()

class SetPasswordFromTokenForm(PasswordMatchForm):
  token = forms.CharField(min_length=20, strip=True)
  uid = forms.CharField()

class OrganizationForm(forms.Form):
  email = forms.EmailField()
  organizationName = forms.CharField(max_length=64)

class EmailForm(forms.Form):
  email = forms.EmailField()

class EmailTokenForm(EmailForm):
  token = forms.CharField(min_length=6, strip=True)

class ValidateTokenForm(forms.Form):
  token = forms.CharField(min_length=20, strip=True)
  uid = forms.CharField()

class ValidationResponseForm(forms.Form):
  token = forms.CharField(min_length=20, strip=True)
  uid = forms.CharField()
  activate = forms.BooleanField(required=False, initial=False)

class CreateAdminForm(forms.Form):
  organization = forms.CharField()
  email = forms.EmailField()