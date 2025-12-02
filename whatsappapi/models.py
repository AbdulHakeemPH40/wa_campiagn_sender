"""
WhatsApp API Models
Contact Lists and related data
"""

from django.db import models
from django.conf import settings
from django.utils import timezone


class ContactList(models.Model):
    """
    Uploaded contact list (CSV/XLSX file)
    Stores phone numbers for WhatsApp campaigns
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='contact_lists')
    name = models.CharField(max_length=255)  # User-given name
    file_name = models.CharField(max_length=255)  # Original filename
    country_code = models.CharField(max_length=10, blank=True, null=True)  # e.g., +91
    total_contacts = models.IntegerField(default=0)
    valid_contacts = models.IntegerField(default=0)  # Verified on WhatsApp
    
    # Store available fields from CSV headers (JSON)
    available_fields = models.JSONField(default=list, blank=True)  # ['first_name', 'last_name', 'email', 'company', 'city']
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        db_table = 'contact_lists'
    
    def __str__(self):
        return f"{self.name} ({self.total_contacts} contacts)"


class Contact(models.Model):
    """
    Individual contact in a contact list
    """
    contact_list = models.ForeignKey(ContactList, on_delete=models.CASCADE, related_name='contacts')
    phone_number = models.CharField(max_length=20, db_index=True)  # With country code (required)
    
    # Store all CSV fields as JSON (dynamic fields)
    fields = models.JSONField(default=dict, blank=True)  # {'first_name': 'John', 'company': 'ABC Corp', 'city': 'NYC'}
    
    # Legacy fields for backward compatibility (optional)
    first_name = models.CharField(max_length=255, blank=True, null=True)
    last_name = models.CharField(max_length=255, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    
    # WhatsApp verification
    is_on_whatsapp = models.BooleanField(default=False)
    whatsapp_verified_at = models.DateTimeField(null=True, blank=True)
    
    # Custom fields from CSV (flexible) - kept for backward compatibility
    custom_field_1 = models.CharField(max_length=255, blank=True, null=True)
    custom_field_2 = models.CharField(max_length=255, blank=True, null=True)
    custom_field_3 = models.CharField(max_length=255, blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'contacts'
        unique_together = ['contact_list', 'phone_number']
    
    def __str__(self):
        full_name = f"{self.first_name or ''} {self.last_name or ''}".strip()
        return f"{full_name or 'N/A'} - {self.phone_number}"


class CampaignTemplate(models.Model):
    """
    Draft and saved campaign templates
    """
    STATUS_CHOICES = (
        ('draft', 'Draft'),
        ('active', 'Active'),
    )
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='campaign_templates')
    name = models.CharField(max_length=255)  # Template name
    message = models.TextField()  # Message content with variables
    
    # Contact list selection
    contact_list = models.ForeignKey(ContactList, on_delete=models.SET_NULL, null=True, blank=True, related_name='templates')
    
    # Attachment
    attachment = models.FileField(upload_to='campaign_attachments/', null=True, blank=True)
    attachment_type = models.CharField(max_length=20, blank=True, null=True)  # image, video, document
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-updated_at']
        db_table = 'campaign_templates'
    
    def __str__(self):
        return f"{self.name} ({self.status})"


# --- Moderation & Enforcement Models ---

class UserModerationProfile(models.Model):
    """
    Per-user moderation state for admin enforcement.
    Admin can set warning levels and permanent block.
    """
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='moderation_profile')
    warnings_count = models.IntegerField(default=0)
    permanently_blocked = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'user_moderation_profiles'
        verbose_name = 'User Moderation Profile'
        verbose_name_plural = 'User Moderation Profiles'

    def __str__(self):
        status = 'Blocked' if self.permanently_blocked else f"Warnings {self.warnings_count}"
        return f"{self.user} - {status}"


class ModerationIncident(models.Model):
    """
    Record of a campaign send attempt with moderation context.
    Shown in admin so actions can be taken on the user.
    """
    STATUS_CHOICES = (
        ('blocked', 'Blocked'),
        ('review', 'Requires Review'),
        ('allowed', 'Allowed'),
    )

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='moderation_incidents')
    campaign_name = models.CharField(max_length=255)
    contact_list = models.ForeignKey(ContactList, on_delete=models.SET_NULL, null=True, blank=True, related_name='moderation_incidents')
    message_text = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, db_index=True)
    risk_score = models.IntegerField(default=0)
    reasons_text = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        db_table = 'moderation_incidents'
        verbose_name = 'Moderation Incident'
        verbose_name_plural = 'Moderation Incidents'

    def __str__(self):
        return f"{self.user} - {self.status} ({self.risk_score}) at {self.created_at}"
