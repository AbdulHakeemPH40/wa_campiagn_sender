from django.contrib import admin
from .models import Subscription, Payment, Invoice, SubscriptionPlan

@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ('user', 'plan', 'status', 'seats', 'created_at', 'end_date', 'cancelled_at')
    list_filter = ('status', 'created_at', 'end_date', 'cancelled_at')
    search_fields = ('user__email', 'user__full_name', 'plan__name', 'subscription_number')
    raw_id_fields = ('user', 'plan')
    readonly_fields = ('created_at', 'cancelled_at')
    fieldsets = (
        ('Basic Info', {
            'fields': ('user', 'plan', 'status', 'seats')
        }),
        ('Dates', {
            'fields': ('created_at', 'end_date', 'cancelled_at')
        }),
        ('Cancellation', {
            'fields': ('cancel_reason',),
            'classes': ('collapse',)
        }),
        ('Additional', {
            'fields': ('subscription_number',)
        })
    )

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('user', 'subscription', 'display_amount', 'status', 'payment_gateway', 'payment_method', 'payment_date', 'transaction_id')
    list_filter = ('status', 'payment_gateway', 'payment_method', 'payment_date', 'currency')
    search_fields = ('user__email', 'transaction_id', 'subscription__subscription_number', 'razorpay_payment_id', 'paypal_order_id')
    raw_id_fields = ('user', 'subscription')
    readonly_fields = ('payment_date',)
    
    def display_amount(self, obj):
        """Display amount with currency symbol based on payment gateway"""
        if obj.currency == 'INR' or obj.payment_gateway == 'razorpay':
            return f"₹{obj.amount:.0f}"
        else:
            return f"${obj.amount:.2f}"
    display_amount.short_description = 'Amount'
    display_amount.admin_order_field = 'amount'

@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'user', 'payment', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('invoice_number', 'user__email', 'payment__transaction_id')
    raw_id_fields = ('user', 'payment')
    readonly_fields = ('created_at',)

@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'formatted_price', 'currency', 'duration_days', 'is_active')
    list_filter = ('is_active', 'currency', 'duration_days')
    search_fields = ('name', 'description')
    fieldsets = (
        ('Basic Info', {
            'fields': ('name', 'description', 'is_active')
        }),
        ('Pricing', {
            'fields': ('price', 'currency', 'duration_days')
        }),
        ('Features', {
            'fields': ('features',)
        })
    )
    
    def formatted_price(self, obj):
        """Display price with currency symbol"""
        return obj.get_formatted_price()
    formatted_price.short_description = 'Price'
