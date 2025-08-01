from django.db import models
from django.conf import settings
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
