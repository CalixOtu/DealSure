from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import ReadOnlyPasswordHashField
from .models import BusinessProfile
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

User = get_user_model()

class RegistrationForm(forms.ModelForm):
    password1 = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"})
    )
    password2 = forms.CharField(
        label="Repeat Password",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"})
    )
    role = forms.ChoiceField(
        choices=User.Role.choices,
        widget=forms.RadioSelect
    )
    terms_accepted = forms.BooleanField(
        label=_('I accept the Terms of Service'),
        required=True
    )

    class Meta:
        model = User
        fields = [
            'email', 'first_name', 'last_name', 'phone', 'role', 'terms_accepted'
        ]
        widgets = {
            'email': forms.EmailInput(attrs={"autocomplete": "email"}),
            'first_name': forms.TextInput(),
            'last_name': forms.TextInput(),
            'phone': forms.TextInput(),
        }

    def clean_email(self):
        email = self.cleaned_data.get('email').lower()
        if User.objects.filter(email=email).exists():
            raise ValidationError("A user with that email already exists.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get('password1')
        p2 = cleaned_data.get('password2')
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError({'password2': "Passwords do not match."})
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        user.role = self.cleaned_data["role"]
        user.terms_accepted = self.cleaned_data["terms_accepted"]
        user.email = self.cleaned_data["email"].lower()
        user.kyc_status = User.KYCStatus.NOT_STARTED
        if commit:
            user.save()
        return user


class UserLoginForm(forms.Form):
    email = forms.EmailField(widget=forms.EmailInput(attrs={"autocomplete": "email"}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}))


class UserProfileForm(forms.ModelForm):
    email = forms.EmailField(disabled=True, required=False)

    class Meta:
        model = User
        fields = [
            'email', 'first_name', 'last_name', 'phone'
        ]


class BusinessProfileForm(forms.ModelForm):

    class Meta:
        model = BusinessProfile
        exclude = ('user', 'stellar_wallet_verified', 'wallet_verified_at', 'created_at', 'updated_at')
        widgets = {
            'description': forms.Textarea(attrs={"rows": 3}),
            'address': forms.Textarea(attrs={"rows": 2}),
        }
