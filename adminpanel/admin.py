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
    list_display = ('user', 'subscription', 'amount', 'status', 'payment_method', 'payment_date', 'transaction_id')
    list_filter = ('status', 'payment_method', 'payment_date')
    search_fields = ('user__email', 'transaction_id', 'subscription__subscription_number')
    raw_id_fields = ('user', 'subscription')
    readonly_fields = ('payment_date',)

@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'user', 'payment', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('invoice_number', 'user__email', 'payment__transaction_id')
    raw_id_fields = ('user', 'payment')
    readonly_fields = ('created_at',)

@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'price', 'duration_days', 'is_active')
    list_filter = ('is_active', 'duration_days')
    search_fields = ('name', 'description')
    fieldsets = (
        ('Basic Info', {
            'fields': ('name', 'description', 'is_active')
        }),
        ('Pricing', {
            'fields': ('price', 'duration_days')
        }),
        ('Features', {
            'fields': ('features',)
        })
    )
