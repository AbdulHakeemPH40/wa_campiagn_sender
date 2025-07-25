from django.contrib import admin
from .models import Order, OrderItem, Address

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
