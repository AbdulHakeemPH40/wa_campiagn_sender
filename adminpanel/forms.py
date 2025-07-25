from django import forms
from sitevisitor.models import CustomUser, WhatsAppNumber
from adminpanel.models import SubscriptionPlan


class UserSearchForm(forms.Form):
    """Simple search box for email or phone"""
    q = forms.CharField(
        label="",
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': 'Search email or phone',
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-button focus:outline-none focus:ring-2 focus:ring-primary/50',
        })
    )


class GrantSubscriptionForm(forms.Form):
    GRANT_CHOICES = [
        ('subscription', 'Grant Subscription Plan'),
        ('free_trial', 'Grant Free Trial (14 days)'),
    ]
    
    grant_type = forms.ChoiceField(
        choices=GRANT_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'mr-2'}),
        initial='subscription'
    )
    plan = forms.ModelChoiceField(
        queryset=SubscriptionPlan.objects.filter(is_active=True), 
        required=False,
        widget=forms.Select(attrs={'class': 'w-full px-3 py-2 border border-gray-300 rounded-md'})
    )
    trial_days = forms.IntegerField(
        initial=14,
        min_value=1,
        max_value=365,
        widget=forms.NumberInput(attrs={'class': 'w-full px-3 py-2 border border-gray-300 rounded-md'})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['plan'].label_from_instance = lambda obj: f"{obj.name} (${obj.price})"
    
    def clean(self):
        cleaned_data = super().clean()
        grant_type = cleaned_data.get('grant_type')
        plan = cleaned_data.get('plan')
        
        if grant_type == 'subscription' and not plan:
            raise forms.ValidationError('Please select a subscription plan.')
        
        return cleaned_data
