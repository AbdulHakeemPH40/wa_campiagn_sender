from django import forms
from django.contrib.auth.forms import UserCreationForm, PasswordResetForm, SetPasswordForm
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from .models import CustomUser, NewsletterSubscriber, Profile, FreeTrialPhone

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
    
    phone = forms.CharField(
        widget=forms.TextInput(
            attrs={
                'class': 'w-full pl-10 pr-3 py-3 border border-gray-300 !rounded-button text-gray-700 focus:border-primary',
                'placeholder': 'Enter your WhatsApp number'
            }
        )
    )

    terms = forms.BooleanField(
        required=True,
        error_messages={'required': 'You must accept the Terms of Service and Privacy Policy'}
    )

    class Meta(UserCreationForm.Meta):
        model = CustomUser
        fields = ('full_name', 'email', 'phone')

    def clean_phone(self):
        phone = self.cleaned_data.get('phone')
        if not phone:
            return phone
        
        # Normalize phone number the same way as WhatsAppNumber model
        normalized_phone = phone.lstrip('+')
        
        from sitevisitor.models import WhatsAppNumber
        if WhatsAppNumber.objects.filter(number=normalized_phone).exists():
            raise ValidationError("This WhatsApp number is already in use by another account.")
        return phone

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


class WhatsAppNumberForm(forms.Form):
    full_name = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={
            'class': 'appearance-none block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm placeholder-gray-400 focus:outline-none focus:ring-primary focus:border-primary sm:text-sm',
            'placeholder': 'Your Full Name'
        })
    )
    
    whatsapp_number = forms.CharField(
        max_length=20,
        widget=forms.TextInput(attrs={
            'class': 'appearance-none block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm placeholder-gray-400 focus:outline-none focus:ring-primary focus:border-primary sm:text-sm',
            'placeholder': '+1234567890',
            'pattern': r'[\+0-9]+',
            'title': 'Please enter only numbers and the + sign'
        })
    )
    
    def clean_whatsapp_number(self):
        whatsapp_number = self.cleaned_data.get('whatsapp_number')
        if not whatsapp_number:
            raise ValidationError("WhatsApp number is required.")
        
        # Normalize phone number
        normalized_number = whatsapp_number.lstrip('+')
        
        from sitevisitor.models import WhatsAppNumber
        if WhatsAppNumber.objects.filter(number=normalized_number).exists():
            raise ValidationError("This WhatsApp number is already in use by another account.")
        return whatsapp_number
