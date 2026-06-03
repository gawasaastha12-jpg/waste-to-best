# webui/forms.py
from django import forms

class LoginForm(forms.Form):
    email = forms.EmailField(
        label="Email Address",
        widget=forms.EmailInput(attrs={
            'class': 'form-input',
            'placeholder': 'Enter your email address',
            'id': 'login-email',
            'required': 'true'
        })
    )
    password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={
            'class': 'form-input',
            'placeholder': 'Enter your password',
            'id': 'login-password',
            'required': 'true'
        })
    )

class RegisterForm(forms.Form):
    email = forms.EmailField(
        label="Email Address",
        widget=forms.EmailInput(attrs={
            'class': 'form-input',
            'placeholder': 'Enter email address',
            'id': 'register-email',
            'required': 'true'
        })
    )
    password = forms.CharField(
        label="Password",
        min_length=8,
        widget=forms.PasswordInput(attrs={
            'class': 'form-input',
            'placeholder': 'Enter password (min 8 characters)',
            'id': 'register-password',
            'required': 'true'
        })
    )
    display_name = forms.CharField(
        label="Display Name",
        max_length=150,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'Enter full name',
            'id': 'register-name',
            'required': 'true'
        })
    )
    phone_number = forms.CharField(
        label="Phone Number",
        required=False,
        max_length=20,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'Enter phone number (optional)',
            'id': 'register-phone'
        })
    )
    address_line = forms.CharField(
        label="Address Line",
        required=False,
        max_length=255,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'Enter address (optional)',
            'id': 'register-address'
        })
    )
    consent = forms.BooleanField(
        label="I consent to WasteTrack+ data processing policy.",
        widget=forms.CheckboxInput(attrs={
            'class': 'form-checkbox',
            'id': 'register-consent',
            'required': 'true'
        })
    )
