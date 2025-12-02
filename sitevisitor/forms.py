from django import forms
from django.contrib.auth.forms import UserCreationForm, PasswordResetForm, SetPasswordForm
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from .models import CustomUser, NewsletterSubscriber, Profile

User = get_user_model()

class LoginForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(
            attrs={
                'class': 'w-full pl-10 pr-3 py-3 border border-gray-300 !rounded-button text-gray-700 focus:border-primary',
                'placeholder': 'Enter your email'
            }
        )
    )
    password = forms.CharField(
        widget=forms.PasswordInput(
            attrs={
                'class': 'w-full pl-10 pr-10 py-3 border border-gray-300 !rounded-button text-gray-700 focus:border-primary',
                'placeholder': 'Enter your password'
            }
        )
    )
    remember_me = forms.BooleanField(required=False)

class SignupForm(UserCreationForm):
    full_name = forms.CharField(
        widget=forms.TextInput(
            attrs={
                'class': 'w-full pl-10 pr-3 py-3 border border-gray-300 !rounded-button text-gray-700 focus:border-primary',
                'placeholder': 'Enter your full name'
            }
        )
    )
    email = forms.EmailField(
        widget=forms.EmailInput(
            attrs={
                'class': 'w-full pl-10 pr-3 py-3 border border-gray-300 !rounded-button text-gray-700 focus:border-primary',
                'placeholder': 'Enter your email address'
            }
        )
    )

    

    password1 = forms.CharField(
        widget=forms.PasswordInput(
            attrs={
                'class': 'w-full pl-10 pr-10 py-3 border border-gray-300 !rounded-button text-gray-700 focus:border-primary',
                'placeholder': 'Create a password'
            }
        )
    )
    password2 = forms.CharField(
        widget=forms.PasswordInput(
            attrs={
                'class': 'w-full pl-10 pr-10 py-3 border border-gray-300 !rounded-button text-gray-700 focus:border-primary',
                'placeholder': 'Confirm your password'
            }
        )
    )
    
    terms = forms.BooleanField(
        required=True,
        error_messages={'required': 'You must accept the Terms of Service and Privacy Policy'}
    )

    class Meta(UserCreationForm.Meta):
        model = CustomUser
        fields = ('full_name', 'email')

    def clean_email(self):
        """Ensure the email is unique (case-insensitive) and normalised to lowercase."""
        email = self.cleaned_data.get('email').lower() if self.cleaned_data.get('email') else ''
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("This email is already registered.")
        return email

    def save(self, commit=True):
        """Save user with normalised email."""
        user = super().save(commit=False)
        # Normalise email to lowercase to avoid duplicates with different cases
        user.email = self.cleaned_data.get('email').lower()
        if commit:
            user.save()
        return user

class CustomPasswordResetForm(PasswordResetForm):
    email = forms.EmailField(
        widget=forms.EmailInput(
            attrs={
                'class': 'w-full pl-10 pr-3 py-3 border border-gray-300 !rounded-button text-gray-700 focus:border-primary',
                'placeholder': 'Enter your email address'
            }
        )
    )

class CustomSetPasswordForm(SetPasswordForm):
    new_password1 = forms.CharField(
        widget=forms.PasswordInput(
            attrs={
                'class': 'w-full pl-10 pr-10 py-3 border border-gray-300 !rounded-button text-gray-700 focus:border-primary',
                'placeholder': 'Enter new password'
            }
        )
    )
    new_password2 = forms.CharField(
        widget=forms.PasswordInput(
            attrs={
                'class': 'w-full pl-10 pr-10 py-3 border border-gray-300 !rounded-button text-gray-700 focus:border-primary',
                'placeholder': 'Confirm new password'
            }
        )
    )

class OTPVerificationForm(forms.Form):
    otp = forms.CharField(
        max_length=6,
        min_length=6,
        widget=forms.TextInput(
            attrs={
                'class': 'w-full pl-10 pr-3 py-3 border border-gray-300 !rounded-button text-gray-700 focus:border-primary',
                'placeholder': 'Enter 6-digit OTP'
            }
        )
    )


class NewsletterForm(forms.ModelForm):
    class Meta:
        model = NewsletterSubscriber
        fields = ['email']


class ContactForm(forms.Form):
    name = forms.CharField(max_length=100, widget=forms.TextInput(attrs={
        'class': 'mt-1 block w-full px-4 py-2 border border-gray-300 rounded-md shadow-sm focus:ring-primary focus:border-primary',
        'placeholder': 'Your Name'
    }))
    email = forms.EmailField(widget=forms.EmailInput(attrs={
        'class': 'mt-1 block w-full px-4 py-2 border border-gray-300 rounded-md shadow-sm focus:ring-primary focus:border-primary',
        'placeholder': 'Your Email'
    }))
    subject = forms.CharField(max_length=100, widget=forms.TextInput(attrs={
        'class': 'mt-1 block w-full px-4 py-2 border border-gray-300 rounded-md shadow-sm focus:ring-primary focus:border-primary',
        'placeholder': 'Subject'
    }))
    message = forms.CharField(widget=forms.Textarea(attrs={
        'class': 'mt-1 block w-full px-4 py-2 border border-gray-300 rounded-md shadow-sm focus:ring-primary focus:border-primary',
        'rows': 5,
        'placeholder': 'Your Message'
    }))


class SocialSignupForm(forms.Form):
    """Form for collecting full name during social authentication signup"""
    full_name = forms.CharField(
        max_length=40,
        required=True,
        widget=forms.TextInput(
            attrs={
                'class': 'w-full pl-10 pr-3 py-3 border border-gray-300 !rounded-button text-gray-700 focus:border-primary',
                'placeholder': 'Enter your full name',
                'maxlength': '40'
            }
        )
    )
