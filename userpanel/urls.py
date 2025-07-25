from django.urls import path
from . import views
from .webhook_handler import paypal_webhook_handler

app_name = 'userpanel'

urlpatterns = [
    # path('simulate-paypal-success/', views.simulate_paypal_success, name='simulate_paypal_success'),
    # path('simulate-paypal-failure/', views.simulate_paypal_failure, name='simulate_paypal_failure'),
    path('logout/', views.logout_view, name='logout'),
    path('', views.dashboard, name='dashboard'),
    path('orders/', views.orders, name='orders'),
    path('orders/<int:order_id>/', views.order_detail, name='order_detail'),
    path('orders/<str:order_id>/invoice/', views.view_order_invoice, name='order_invoice'),
    path('addresses/', views.addresses, name='addresses'),
    path('settings/', views.settings_view, name='settings'),
    path('change-password/', views.change_password_view, name='change_password'),
    path('add-whatsapp-number/', views.add_whatsapp_number, name='add_whatsapp_number'),
    path('remove-whatsapp-number/<int:whatsapp_number_id>/', views.remove_whatsapp_number, name='remove_whatsapp_number'),
    path('pricing/', views.pricing_view, name='pricing'),
    path('cart/', views.cart_view, name='cart'),
    path('add-to-cart/', views.add_to_cart_view, name='add_to_cart'),
    # PayPal URLs
    path('paypal-redirect/', views.direct_paypal_redirect, name='direct_paypal_redirect'),
    path('paypal/return/', views.paypal_return, name='paypal_return'),
    path('paypal/cancel/', views.paypal_cancel, name='paypal_cancel'),
    path('paypal-success/', views.paypal_success_handler, name='paypal_success_handler'),
    # PayPal REST API URLs (legacy support)
    path('payment/success/', views.paypal_return, name='payment_success'),
    path('payment/cancel/', views.paypal_cancel, name='payment_cancel'),
    path('addresses/add/', views.add_address, name='add_address'),
    path('addresses/delete/<int:address_id>/', views.delete_address, name='delete_address'),
    path('addresses/set-default/<int:address_id>/<str:address_type>/', views.set_default_address, name='set_default_address'),
    path('addresses/edit/<int:address_id>/', views.edit_address, name='edit_address'),
    path('addresses/get-data/<int:address_id>/', views.get_address_data, name='get_address_data'),
    path('start-free-trial/', views.start_free_trial, name='start_free_trial'),
    # PayPal Webhook
    path('paypal-webhook/', paypal_webhook_handler, name='paypal_webhook'),

]
