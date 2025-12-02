from django import forms
from django.contrib.auth.forms import PasswordChangeForm
from sitevisitor.models import CustomUser, Profile
from .models import Address

class UserProfileUpdateForm(forms.ModelForm):
    # Fields from CustomUser model are handled by ModelForm
    # Fields from Profile model need to be added explicitly
    profile_picture = forms.ImageField(required=False, 
                                       widget=forms.ClearableFileInput(attrs={'class': 'form-control-file mt-1 w-full text-sm text-gray-900 border border-gray-300 rounded-button cursor-pointer bg-gray-50 focus:outline-none file:bg-primary file:text-white file:border-0 file:py-2 file:px-4 file:mr-4'}))

    class Meta:
        model = CustomUser
        fields = ['full_name'] # Only fields directly on CustomUser

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Populate initial value for profile picture if user instance and profile exist
        if self.instance and self.instance.pk:
            try:
                self.fields['profile_picture'].initial = self.instance.profile.profile_picture
            except Profile.DoesNotExist:
                pass

        # Apply consistent styling for full_name
        self.fields['full_name'].widget.attrs.update({
            'class': 'mt-1 w-full pl-3 pr-3 py-2 border border-gray-300 rounded-button text-gray-700 focus:border-primary'
        })



    def save(self, commit=True):
        user = super().save(commit=False) # Save CustomUser fields (full_name)
        
        if commit:
            user.save()
            
            # Get or create the profile instance for this user
            profile, created = Profile.objects.get_or_create(user=user)
            
            # Save profile_picture
            if 'profile_picture' in self.cleaned_data:
                if self.cleaned_data['profile_picture'] is False: # Check if field was cleared
                    profile.profile_picture.delete(save=False) # Delete file, save profile later
                elif self.cleaned_data['profile_picture'] is not None: # New file uploaded
                    profile.profile_picture = self.cleaned_data['profile_picture']
            
            profile.save() # Save profile changes
            
        return user

class UserPasswordChangeForm(PasswordChangeForm):
    old_password = forms.CharField(
        label=("Old password"),
        strip=False,
        widget=forms.PasswordInput(attrs={'autocomplete': 'current-password', 'autofocus': True, 'class': 'form-input w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-300 focus:ring focus:ring-indigo-200 focus:ring-opacity-50'}),
    )
    new_password1 = forms.CharField(
        label=("New password"),
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password', 'class': 'form-input w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-300 focus:ring focus:ring-indigo-200 focus:ring-opacity-50'}),
        strip=False,
    )
    new_password2 = forms.CharField(
        label=("New password confirmation"),
        strip=False,
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password', 'class': 'form-input w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-300 focus:ring focus:ring-indigo-200 focus:ring-opacity-50'}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for fieldname in ['old_password', 'new_password1', 'new_password2']:
            self.fields[fieldname].help_text = None # Remove default help text

class AddressForm(forms.ModelForm):
    class Meta:
        model = Address
        fields = ['address_line_1', 'address_line_2', 'city', 'state', 'postal_code', 'country', 'is_default_shipping', 'is_default_billing']
        widgets = {
            'address_line_1': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:ring-primary focus:border-primary text-sm', 'placeholder': 'Street address, P.O. box, company name, c/o'}),
            'address_line_2': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:ring-primary focus:border-primary text-sm', 'placeholder': 'Apartment, suite, unit, building, floor, etc.'}),
            'city': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:ring-primary focus:border-primary text-sm', 'placeholder': 'City'}),
            'state': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:ring-primary focus:border-primary text-sm', 'placeholder': 'State / Province'}),
            'postal_code': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:ring-primary focus:border-primary text-sm', 'placeholder': 'Postal Code'}),
            'country': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:ring-primary focus:border-primary text-sm', 'placeholder': 'Country'}),
            'is_default_shipping': forms.CheckboxInput(attrs={'class': 'h-4 w-4 text-primary border-gray-300 rounded focus:ring-primary'}),
            'is_default_billing': forms.CheckboxInput(attrs={'class': 'h-4 w-4 text-primary border-gray-300 rounded focus:ring-primary'}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

    def save(self, commit=True):
        address = super().save(commit=False)
        if self.user:
            address.user = self.user
        if commit:
            address.save() # The model's save method handles default logic
        return address

