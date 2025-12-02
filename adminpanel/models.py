from django.db import models
from django.conf import settings
from django.utils import timezone

class Subscription(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, db_index=True)
    plan = models.ForeignKey('SubscriptionPlan', on_delete=models.SET_NULL, null=True, blank=True, related_name='subscriptions')
    status = models.CharField(max_length=20, default='active', db_index=True) # Consider adding choices for clarity: ('active', 'Active'), ('cancelled', 'Cancelled'), ('expired', 'Expired')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    end_date = models.DateTimeField(null=True, blank=True, db_index=True)
    cancelled_at = models.DateTimeField(null=True, blank=True) # New field: Timestamp when the subscription was cancelled
    cancel_reason = models.TextField(blank=True, null=True) # New field: Reason for cancellation
    subscription_number = models.CharField(max_length=100, blank=True, null=True)
    seats = models.PositiveIntegerField(default=1)

    def cancel(self, reason=None):
        """Marks the subscription as cancelled and sets its end_date to now."""
        self.status = 'cancelled'
        self.end_date = timezone.now() # Immediately end the subscription
        self.cancelled_at = timezone.now()
        self.cancel_reason = reason
        self.save()  # Number of seats/licenses granted

    class Meta:
        # Composite indexes for optimal PayPal payment processing queries
        indexes = [
            models.Index(fields=['user', 'status', 'end_date']),  # Primary PayPal subscription check
            models.Index(fields=['status', 'end_date']),          # Active subscription queries
            models.Index(fields=['user', 'status']),              # User subscription status
            models.Index(fields=['created_at', 'status']),        # Recent subscriptions
        ]
        # Database table optimization
        db_table = 'adminpanel_subscription'
        verbose_name = 'Subscription'
        verbose_name_plural = 'Subscriptions'

    def __str__(self):
        plan_name = self.plan.name if self.plan else 'No Plan'
        return f"{self.user.email} - {plan_name} ({self.status})"

class Payment(models.Model):
    PAYMENT_GATEWAY_CHOICES = [
        ('paypal', 'PayPal'),
        ('razorpay', 'Razorpay'),
    ]
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    subscription = models.ForeignKey('Subscription', on_delete=models.SET_NULL, null=True, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='USD')  # USD or INR
    status = models.CharField(max_length=20, default='completed')
    payment_date = models.DateTimeField(auto_now_add=True)
    transaction_id = models.CharField(max_length=100, blank=True, null=True)
    payment_method = models.CharField(max_length=50, blank=True, null=True)
    
    # Payment Gateway
    payment_gateway = models.CharField(max_length=20, choices=PAYMENT_GATEWAY_CHOICES, default='paypal')
    
    # Razorpay-specific fields
    razorpay_payment_id = models.CharField(max_length=100, blank=True, null=True)
    razorpay_order_id = models.CharField(max_length=100, blank=True, null=True)
    razorpay_signature = models.CharField(max_length=255, blank=True, null=True)
    
    # PayPal-specific fields (for clarity)
    paypal_order_id = models.CharField(max_length=100, blank=True, null=True)
    paypal_payer_id = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return f"Payment {self.id} - {self.user.email} - {self.amount} {self.currency} ({self.status})"

class Invoice(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    payment = models.ForeignKey('Payment', on_delete=models.CASCADE)
    invoice_number = models.CharField(max_length=100)

    def __str__(self):
        return self.invoice_number
    created_at = models.DateTimeField(auto_now_add=True)

class SubscriptionPlan(models.Model):
    CURRENCY_CHOICES = [
        ('USD', 'US Dollar'),
        ('INR', 'Indian Rupee'),
    ]
    
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default='USD')
    duration_days = models.IntegerField(default=30)
    features = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    def get_currency_symbol(self):
        """Return currency symbol based on currency code"""
        return '₹' if self.currency == 'INR' else '$'
    
    def get_formatted_price(self):
        """Return price with currency symbol"""
        symbol = self.get_currency_symbol()
        return f"{symbol}{self.price}"

    def __str__(self):
        return self.name
