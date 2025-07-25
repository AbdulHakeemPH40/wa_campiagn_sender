from django.db import models

# Create your models here.
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings

class CustomUserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError(_('The Email field must be set'))
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        
        return self.create_user(email, password, **extra_fields)

class CustomUser(AbstractUser):
    username = None
    email = models.EmailField(_('email address'), unique=True)
    full_name = models.CharField(max_length=255)
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    is_email_verified = models.BooleanField(default=False)


    # Add related_name to avoid clashes
    groups = models.ManyToManyField(
        'auth.Group',
        verbose_name=_('groups'),
        blank=True,
        help_text=_(            'The groups this user belongs to. A user will get all permissions '
            'granted to each of their groups.'
        ),
        related_name="customuser_set",  # Unique related_name
        related_query_name="user",
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        verbose_name=_('user permissions'),
        blank=True,
        help_text=_('Specific permissions for this user.'),
        related_name="customuser_permissions_set",  # Unique related_name (made it different from groups)
        related_query_name="user",
    )

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['full_name']

    objects = CustomUserManager()

    def get_full_name(self):
        """Return the user's display name (fallback to email)."""
        return self.full_name or self.email

    def get_short_name(self):
        """Return a short version of the name."""
        return (self.full_name.split(" ")[0] if self.full_name else self.email)

    def __str__(self):
        return self.email

class Profile(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='profile')

    profile_picture = models.ImageField(upload_to='profile_pics/', blank=True, null=True)
    date_joined = models.DateTimeField(auto_now_add=True)
    # One-time 14-day free trial fields
    free_trial_start = models.DateField(null=True, blank=True)
    free_trial_end = models.DateField(null=True, blank=True)
    free_trial_cancelled = models.BooleanField(default=False)  # Flag to track admin cancellations

    # Helper properties
    @property
    def free_trial_used(self):
        """Returns True if the user has ever started a free trial."""
        return bool(self.free_trial_end)

    @property
    def on_free_trial(self):
        from django.utils import timezone
        from userpanel.timezone_utils import get_user_local_date
        # Use get_user_local_date() to respect user's timezone
        # Also check if the trial has been cancelled by admin
        return self.free_trial_end and self.free_trial_end >= get_user_local_date() and not self.free_trial_cancelled
        
    @property
    def free_trial_cancelled(self):
        """Returns True if the free trial was cancelled by an admin (end date is today with 0 days remaining)."""
        from userpanel.timezone_utils import get_user_local_date
        today = get_user_local_date()
        return self.free_trial_end and self.free_trial_end == today and self.days_until_trial_end == 0
    
    @property
    def days_until_trial_end(self):
        """Returns the number of days remaining in the free trial."""
        if not self.free_trial_end:
            return 0
        from userpanel.timezone_utils import get_user_local_date
        # Use get_user_local_date() to respect user's timezone
        today = get_user_local_date()
        if self.free_trial_end >= today:
            return (self.free_trial_end - today).days
        return 0

    @property
    def has_active_subscription(self):
        """
        Returns True if the user has an active paid subscription OR processing payment.
        Processing means PayPal payment received but held - user should get access.
        """
        from django.utils import timezone
        from adminpanel.models import Subscription
        from userpanel.models import Order

        # Check for active subscription
        if Subscription.objects.filter(user=self.user, status='active').exists():
            return True
            
        # Also check for processing orders (PayPal payment received but held)
        return Order.objects.filter(
            user=self.user, 
            status__in=['processing', 'completed'],
            paypal_txn_id__isnull=False
        ).exists()

    @property
    def whatsapp_number(self):
        """Returns the user's primary WhatsApp number, or None if not set."""
        primary = self.whatsapp_numbers.filter(is_primary=True).first()
        if primary:
            return primary.number
        # Fallback to any WhatsApp number if no primary marked
        any_number = self.whatsapp_numbers.first()
        return any_number.number if any_number else None

    def __str__(self):
        return f"{self.user.email}'s Profile"

class WhatsAppNumber(models.Model):
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='whatsapp_numbers')
    number = models.CharField(max_length=20, unique=True)
    is_verified = models.BooleanField(default=False)
    is_primary = models.BooleanField(default=False)
    is_active = models.BooleanField(default=False)  # Subscription activation status
    created_at = models.DateTimeField(auto_now_add=True)
    
    def normalize_number(self):
        """Remove + prefix for consistent storage"""
        return self.number.lstrip('+')
    
    def save(self, *args, **kwargs):
        # Normalize number by removing + prefix
        self.number = self.normalize_number()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.number

    class Meta:
        verbose_name = "WhatsApp Number"
        verbose_name_plural = "WhatsApp Numbers"
        ordering = ['-created_at']

class EmailVerification(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    token = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    
    def __str__(self):
        return f"Verification for {self.user.email}"

class PasswordReset(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    token = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    
    def __str__(self):
        return f"Password reset for {self.user.email}"

class OTPVerification(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    otp = models.CharField(max_length=6)
    purpose = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    
    def __str__(self):
        return f"OTP for {self.user.email} ({self.purpose})"

class FreeTrialPhone(models.Model):
    """Stores phone numbers that have already consumed the free trial."""
    phone = models.CharField(max_length=20, unique=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    used_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.phone


class NewsletterSubscriber(models.Model):
    email = models.EmailField(unique=True)
    subscribed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.email


class ContactMessage(models.Model):
    name = models.CharField(max_length=100)
    email = models.EmailField()
    subject = models.CharField(max_length=150)
    message = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    def __str__(self):
        return f'Message from {self.name} - {self.subject}'

    class Meta:
        ordering = ['-timestamp']
