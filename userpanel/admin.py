from django.contrib import admin
from .models import Order, OrderItem, Address, WASenderSession, WASenderMessage, WASenderCampaign

class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ('total_price',)

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('order_id', 'user', 'status', 'total', 'payment_method', 'created_at', 'updated_at')
    list_filter = ('status', 'payment_method', 'created_at', 'updated_at')
    search_fields = ('order_id', 'user__email', 'user__full_name', 'paypal_txn_id')
    raw_id_fields = ('user',)
    readonly_fields = ('order_id', 'created_at', 'updated_at')
    inlines = [OrderItemInline]
    fieldsets = (
        ('Order Info', {
            'fields': ('order_id', 'user', 'status', 'paypal_txn_id')
        }),
        ('Pricing', {
            'fields': ('subtotal', 'discount', 'total')
        }),
        ('Shipping Address', {
            'fields': ('shipping_name', 'shipping_address', 'shipping_city', 'shipping_state', 'shipping_postal_code', 'shipping_country')
        }),
        ('Payment Info', {
            'fields': ('payment_method', 'card_last4', 'card_expiry')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        })
    )

@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ('order', 'product_name', 'quantity', 'unit_price', 'total_price')
    list_filter = ('order__status', 'order__created_at')
    search_fields = ('product_name', 'order__order_id', 'order__user__email')
    raw_id_fields = ('order',)
    readonly_fields = ('total_price',)

@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ('user', 'address_line_1', 'city', 'state', 'country', 'is_default_shipping', 'is_default_billing')
    list_filter = ('country', 'state', 'is_default_shipping', 'is_default_billing', 'created_at')
    search_fields = ('user__email', 'user__full_name', 'address_line_1', 'city', 'postal_code')
    raw_id_fields = ('user',)
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        ('User', {
            'fields': ('user',)
        }),
        ('Address', {
            'fields': ('address_line_1', 'address_line_2', 'city', 'state', 'postal_code', 'country')
        }),
        ('Defaults', {
            'fields': ('is_default_shipping', 'is_default_billing')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        })
    )


# WASender API Models

@admin.register(WASenderSession)
class WASenderSessionAdmin(admin.ModelAdmin):
    list_display = ('user', 'session_name', 'phone_number', 'status', 'messages_sent_today', 'messages_sent_this_month', 'created_at')
    list_filter = ('status', 'account_protection_enabled', 'created_at')
    search_fields = ('user__email', 'session_id', 'session_name', 'phone_number')
    raw_id_fields = ('user',)
    readonly_fields = ('session_id', 'created_at', 'connected_at', 'disconnected_at', 'last_activity_at', 'last_message_at')
    fieldsets = (
        ('User & Session', {
            'fields': ('user', 'session_id', 'session_name', 'phone_number', 'status')
        }),
        ('API Configuration', {
            'fields': ('api_token', 'webhook_url', 'account_protection_enabled')
        }),
        ('Usage Statistics', {
            'fields': ('messages_sent_today', 'messages_sent_this_month', 'last_reset_date')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'connected_at', 'disconnected_at', 'last_activity_at', 'last_message_at')
        })
    )


@admin.register(WASenderMessage)
class WASenderMessageAdmin(admin.ModelAdmin):
    list_display = ('user', 'recipient', 'message_type', 'status', 'created_at', 'sent_at')
    list_filter = ('message_type', 'status', 'created_at')
    search_fields = ('user__email', 'recipient', 'message_id', 'content')
    raw_id_fields = ('user', 'session')
    readonly_fields = ('message_id', 'created_at', 'sent_at', 'delivered_at', 'read_at')
    fieldsets = (
        ('Message Info', {
            'fields': ('session', 'user', 'message_id', 'recipient', 'message_type', 'status')
        }),
        ('Content', {
            'fields': ('content', 'caption', 'metadata')
        }),
        ('Error', {
            'fields': ('error_message',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'sent_at', 'delivered_at', 'read_at')
        })
    )


@admin.register(WASenderCampaign)
class WASenderCampaignAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'status', 'total_recipients', 'messages_sent', 'messages_delivered', 'messages_failed', 'created_at')
    list_filter = ('status', 'message_type', 'created_at')
    search_fields = ('name', 'user__email', 'description')
    raw_id_fields = ('user', 'session')
    readonly_fields = ('created_at', 'updated_at', 'started_at', 'completed_at')
    fieldsets = (
        ('Campaign Info', {
            'fields': ('user', 'session', 'name', 'description', 'status')
        }),
        ('Message Template', {
            'fields': ('message_type', 'message_template', 'media_url')
        }),
        ('Recipients', {
            'fields': ('recipients', 'total_recipients')
        }),
        ('Statistics', {
            'fields': ('messages_sent', 'messages_delivered', 'messages_failed')
        }),
        ('Scheduling', {
            'fields': ('scheduled_at', 'started_at', 'completed_at')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        })
    )
