from django.db import models
from django.conf import settings
from django.utils import timezone
import uuid
from datetime import datetime

STATUS_CHOICES = (
    ('pending', 'Pending'),
    ('processing', 'Processing'),
    ('completed', 'Completed'),
    ('shipped', 'Shipped'),
    ('delivered', 'Delivered'),
    ('cancelled', 'Cancelled'),
)

class Order(models.Model):
    order_id = models.CharField(max_length=20, unique=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='orders', db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    paypal_txn_id = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    paypal_payment_id = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=10, decimal_places=2)
    shipping_name = models.CharField(max_length=100, blank=True, null=True)
    shipping_address = models.TextField(blank=True, null=True)
    shipping_city = models.CharField(max_length=100, blank=True, null=True)
    shipping_state = models.CharField(max_length=100, blank=True, null=True)
    shipping_postal_code = models.CharField(max_length=20, blank=True, null=True)
    shipping_country = models.CharField(max_length=100, blank=True, null=True)
    payment_method = models.CharField(max_length=50, blank=True, null=True)
    card_last4 = models.CharField(max_length=4, blank=True, null=True)
    card_expiry = models.CharField(max_length=7, blank=True, null=True)
    
    def save(self, *args, **kwargs):
        # Check if status is changing to completed and we need to generate invoice number
        status_changed_to_completed = False
        if self.pk:  # Existing order
            try:
                old_order = Order.objects.get(pk=self.pk)
                if old_order.status != 'completed' and self.status == 'completed':
                    status_changed_to_completed = True
            except Order.DoesNotExist:
                pass
        
        # Generate order_id for new orders or when status changes to completed
        if not self.order_id:
            # Use short UUID for pending orders
            import uuid
            self.order_id = 'P{}'.format(str(uuid.uuid4())[:8].upper())
        
        # Generate invoice number when order is completed
        if (self.status == 'completed' and 
            (not self.pk or status_changed_to_completed) and 
            not self.order_id.startswith('#')):
            from datetime import datetime
            year = datetime.now().strftime('%Y')
            # Get count of completed orders with invoice numbers this year
            count = Order.objects.filter(
                order_id__startswith='#{}'.format(year), 
                status='completed'
            ).count() + 1
            self.order_id = '#{}{:06d}'.format(year, count)
        
        super().save(*args, **kwargs)
    
    class Meta:
        # Composite indexes for optimal PayPal payment processing queries
        indexes = [
            models.Index(fields=['user', 'status']),              # User order status queries
            models.Index(fields=['status', 'created_at']),        # Recent orders by status
            models.Index(fields=['user', 'status', 'created_at']), # User recent orders
            models.Index(fields=['paypal_payment_id', 'status']),  # PayPal payment tracking
            models.Index(fields=['paypal_txn_id', 'status']),      # PayPal transaction tracking
        ]
        # Database table optimization
        ordering = ['-created_at']
        verbose_name = 'Order'
        verbose_name_plural = 'Orders'

    def __str__(self):
        return '{} - {}'.format(self.order_id, self.user.email)


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product_name = models.CharField(max_length=255)
    product_description = models.TextField(blank=True)
    quantity = models.IntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)
    
    def save(self, *args, **kwargs):
        self.total_price = self.quantity * self.unit_price
        super().save(*args, **kwargs)
    
    def __str__(self):
        return '{} ({}) - {}'.format(self.product_name, self.quantity, self.order.order_id)


class Address(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='addresses')
    address_line_1 = models.CharField(max_length=255)
    address_line_2 = models.CharField(max_length=255, blank=True, null=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100) # Or province
    postal_code = models.CharField(max_length=20)
    country = models.CharField(max_length=100)
    is_default_shipping = models.BooleanField(default=False)
    is_default_billing = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Addresses"
        ordering = ['-is_default_shipping', '-is_default_billing', '-created_at']

    def __str__(self):
        return "{}, {}, {}".format(self.address_line_1, self.city, self.user.email)

    def save(self, *args, **kwargs):
        # Ensure only one default shipping address per user
        if self.is_default_shipping:
            Address.objects.filter(user=self.user, is_default_shipping=True).exclude(pk=self.pk).update(is_default_shipping=False)
        # Ensure only one default billing address per user
        if self.is_default_billing:
            Address.objects.filter(user=self.user, is_default_billing=True).exclude(pk=self.pk).update(is_default_billing=False)
        super().save(*args, **kwargs)


# WASender API Integration Models

class WASenderSession(models.Model):
    """
    WhatsApp session for WASender API integration.
    Each user can have one active session connected to their WhatsApp number.
    """
    SESSION_STATUS_CHOICES = (
        ('pending', 'Pending QR Scan'),
        ('connecting', 'Connecting'),
        ('connected', 'Connected'),
        ('disconnected', 'Disconnected'),
        ('error', 'Error'),
    )
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='wasender_sessions', db_index=True)
    session_id = models.CharField(max_length=100, unique=True, db_index=True)  # WASender session ID
    session_name = models.CharField(max_length=255)
    api_token = models.CharField(max_length=500)  # Encrypted session-specific token
    phone_number = models.CharField(max_length=20, blank=True, null=True)  # Phone entered during session creation
    connected_phone_number = models.CharField(max_length=20, blank=True, null=True)  # Actual WhatsApp number after scan
    status = models.CharField(max_length=20, choices=SESSION_STATUS_CHOICES, default='pending', db_index=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    connected_at = models.DateTimeField(null=True, blank=True)
    disconnected_at = models.DateTimeField(null=True, blank=True)
    last_activity_at = models.DateTimeField(null=True, blank=True)
    
    # Message usage tracking
    messages_sent_today = models.IntegerField(default=0)
    messages_sent_this_month = models.IntegerField(default=0)
    last_message_at = models.DateTimeField(null=True, blank=True)
    last_reset_date = models.DateField(auto_now_add=True)  # For daily reset
    
    # Account Protection (1 message per 5 seconds)
    account_protection_enabled = models.BooleanField(default=True)
    
    # Webhook URL for this session
    webhook_url = models.URLField(max_length=500, blank=True, null=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['session_id']),
            models.Index(fields=['status', 'created_at']),
        ]
        ordering = ['-created_at']
        verbose_name = 'WASender Session'
        verbose_name_plural = 'WASender Sessions'
    
    def __str__(self):
        return f"{self.user.email} - {self.session_name} ({self.status})"
    
    def reset_daily_count(self):
        """Reset daily message count if new day"""
        today = timezone.now().date()
        if self.last_reset_date < today:
            self.messages_sent_today = 0
            self.last_reset_date = today
            self.save(update_fields=['messages_sent_today', 'last_reset_date'])
    
    def can_send_message(self):
        """Check if message can be sent based on rate limits"""
        self.reset_daily_count()
        
        # Check daily limit
        if self.account_protection_enabled:
            daily_limit = 17280  # 720 msg/hr * 24 hrs with account protection
        else:
            daily_limit = 368640  # 15360 msg/hr * 24 hrs without protection
        
        if self.messages_sent_today >= daily_limit:
            return False, "Daily message limit reached"
        
        # Check time between messages (account protection)
        if self.account_protection_enabled and self.last_message_at:
            elapsed = (timezone.now() - self.last_message_at).total_seconds()
            # Use configurable delay from settings (defaults to 5 seconds)
            from django.conf import settings as django_settings
            delay_required = getattr(django_settings, 'WASENDER_SEND_DELAY_SECONDS', 5)
            try:
                delay_required = int(delay_required)
            except Exception:
                delay_required = 5
            if elapsed < delay_required:
                return False, f"Wait {int(delay_required - elapsed)} seconds before next message"
        
        return True, None
    
    def increment_message_count(self):
        """Increment message counters"""
        self.messages_sent_today += 1
        self.messages_sent_this_month += 1
        self.last_message_at = timezone.now()
        self.last_activity_at = timezone.now()
        self.save(update_fields=['messages_sent_today', 'messages_sent_this_month', 'last_message_at', 'last_activity_at'])


class WASenderMessage(models.Model):
    """
    Message sent via WASender API.
    Tracks all messages sent through WhatsApp sessions.
    """
    MESSAGE_TYPE_CHOICES = (
        ('text', 'Text'),
        ('image', 'Image'),
        ('video', 'Video'),
        ('document', 'Document'),
        ('audio', 'Audio'),
        ('sticker', 'Sticker'),
        ('location', 'Location'),
        ('contact', 'Contact'),
    )
    
    MESSAGE_STATUS_CHOICES = (
        ('queued', 'Queued'),
        ('sending', 'Sending'),
        ('sent', 'Sent'),
        ('delivered', 'Delivered'),
        ('read', 'Read'),
        ('failed', 'Failed'),
    )
    
    session = models.ForeignKey(WASenderSession, on_delete=models.CASCADE, related_name='messages', db_index=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='wasender_messages', db_index=True)
    
    # Message details
    message_id = models.CharField(max_length=100, blank=True, null=True, db_index=True)  # WASender message ID
    recipient = models.CharField(max_length=50)  # Phone number
    message_type = models.CharField(max_length=20, choices=MESSAGE_TYPE_CHOICES, default='text')
    content = models.TextField()  # Message text or media URL
    caption = models.TextField(blank=True, null=True)  # For media messages
    
    # Status tracking
    status = models.CharField(max_length=20, choices=MESSAGE_STATUS_CHOICES, default='queued', db_index=True)
    error_message = models.TextField(blank=True, null=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    
    # Metadata
    metadata = models.JSONField(default=dict, blank=True)  # Additional data
    
    class Meta:
        indexes = [
            models.Index(fields=['session', 'status']),
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['message_id']),
        ]
        ordering = ['-created_at']
        verbose_name = 'WASender Message'
        verbose_name_plural = 'WASender Messages'
    
    def __str__(self):
        return f"{self.recipient} - {self.message_type} ({self.status})"


class WASenderCampaign(models.Model):
    """
    Campaign management for bulk WhatsApp messaging.
    Groups multiple messages into organized campaigns.
    """
    CAMPAIGN_STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('draft', 'Draft'),
        ('scheduled', 'Scheduled'),
        ('running', 'Running'),
        ('paused', 'Paused'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    )
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='wasender_campaigns', db_index=True)
    session = models.ForeignKey(WASenderSession, on_delete=models.CASCADE, related_name='campaigns', db_index=True)
    
    # Campaign details
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=CAMPAIGN_STATUS_CHOICES, default='draft', db_index=True)
    
    # Message template
    message_template = models.TextField(db_collation='utf8mb4_unicode_ci')  # Can include variables like {name}, {phone} - supports emojis
    message_type = models.CharField(max_length=20, default='text')
    media_url = models.URLField(max_length=500, blank=True, null=True)  # For media campaigns
    
    # Attachment fields for Cloudinary
    attachment_url = models.URLField(max_length=500, blank=True, null=True)  # Cloudinary public URL
    attachment_type = models.CharField(max_length=20, blank=True, null=True)  # image, video, document, audio
    # Cloudinary public_id captured at upload time for robust signed downloads
    attachment_public_id = models.CharField(max_length=300, blank=True, null=True)
    # Wasender-hosted document URL (pre-uploaded for reliable delivery)
    wasender_document_url = models.URLField(max_length=500, blank=True, null=True)
    
    # Contact list reference
    contact_list = models.ForeignKey('whatsappapi.ContactList', on_delete=models.SET_NULL, null=True, blank=True, related_name='campaigns')
    
    # Recipients (stored as JSON array)
    recipients = models.JSONField(default=list)  # [{"phone": "1234567890", "name": "John"}]
    
    # Metadata for additional campaign data (kept for backward compatibility)
    metadata = models.JSONField(default=dict, blank=True, null=True)
    
    # Background task tracking
    task_id = models.CharField(max_length=100, blank=True, null=True)  # Django-Q task ID
    
    # Stats
    total_recipients = models.IntegerField(default=0)
    messages_sent = models.IntegerField(default=0)
    messages_delivered = models.IntegerField(default=0)
    messages_failed = models.IntegerField(default=0)
    
    # Scheduling
    scheduled_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # Advanced sending controls
    use_advanced_controls = models.BooleanField(default=False)  # Enable advanced batch/delay controls
    random_delay_min = models.IntegerField(default=5)  # Minimum delay in seconds between messages
    random_delay_max = models.IntegerField(default=10)  # Maximum delay in seconds between messages
    batch_size_min = models.IntegerField(default=50)  # Minimum batch size
    batch_size_max = models.IntegerField(default=70)  # Maximum batch size
    batch_cooldown_min = models.FloatField(default=5.0)  # Minimum cooldown between batches (minutes)
    batch_cooldown_max = models.FloatField(default=10.0)  # Maximum cooldown between batches (minutes)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['session', 'status']),
            models.Index(fields=['status', 'created_at']),
        ]
        ordering = ['-created_at']
        verbose_name = 'WASender Campaign'
        verbose_name_plural = 'WASender Campaigns'
    
    def __str__(self):
        return f"{self.name} - {self.status}"
    
    def update_stats(self):
        """Update campaign statistics from messages"""
        messages = WASenderMessage.objects.filter(
            session=self.session,
            created_at__gte=self.created_at
        )
        self.messages_sent = messages.filter(status__in=['sent', 'delivered', 'read']).count()
        self.messages_delivered = messages.filter(status__in=['delivered', 'read']).count()
        self.messages_failed = messages.filter(status='failed').count()
        self.save(update_fields=['messages_sent', 'messages_delivered', 'messages_failed'])


class WASenderIncomingMessage(models.Model):
    """
    Incoming messages received via WASender webhooks.
    Stores messages sent TO the user's WhatsApp number.
    """
    MESSAGE_TYPE_CHOICES = (
        ('text', 'Text'),
        ('image', 'Image'),
        ('video', 'Video'),
        ('document', 'Document'),
        ('audio', 'Audio'),
        ('sticker', 'Sticker'),
        ('location', 'Location'),
        ('contact', 'Contact'),
    )
    
    session = models.ForeignKey(WASenderSession, on_delete=models.CASCADE, related_name='incoming_messages', db_index=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='wasender_incoming_messages', db_index=True)
    
    # Message details
    message_id = models.CharField(max_length=100, unique=True, db_index=True)  # WhatsApp message ID
    sender = models.CharField(max_length=50)  # Phone number who sent the message
    sender_name = models.CharField(max_length=255, blank=True, null=True)  # Push name from WhatsApp
    message_type = models.CharField(max_length=20, choices=MESSAGE_TYPE_CHOICES, default='text')
    content = models.TextField(blank=True, null=True)  # Message text or caption
    media_url = models.URLField(max_length=500, blank=True, null=True)  # Media URL if present
    
    # Metadata
    remote_jid = models.CharField(max_length=100)  # Full JID from WhatsApp
    timestamp = models.BigIntegerField()  # Unix timestamp from WhatsApp
    is_read = models.BooleanField(default=False)  # Marked as read by user
    
    # Timestamps
    received_at = models.DateTimeField(auto_now_add=True, db_index=True)
    
    # Raw webhook data for debugging
    raw_data = models.JSONField(default=dict, blank=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['session', 'received_at']),
            models.Index(fields=['user', 'received_at']),
            models.Index(fields=['sender', 'received_at']),
            models.Index(fields=['message_id']),
            models.Index(fields=['is_read', 'received_at']),
        ]
        ordering = ['-received_at']
        verbose_name = 'Incoming WhatsApp Message'
        verbose_name_plural = 'Incoming WhatsApp Messages'
    
    def __str__(self):
        return f"From {self.sender} ({self.sender_name}) - {self.message_type} at {self.received_at}"
