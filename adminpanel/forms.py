from django import forms
from sitevisitor.models import CustomUser
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
    # Free trial option removed - subscription-based access only
    
    plan = forms.ModelChoiceField(
        queryset=SubscriptionPlan.objects.filter(is_active=True), 
        required=True,
        widget=forms.Select(attrs={'class': 'w-full px-3 py-2 border border-gray-300 rounded-md'})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['plan'].label_from_instance = lambda obj: f"{obj.name} ({obj.get_formatted_price()})"
