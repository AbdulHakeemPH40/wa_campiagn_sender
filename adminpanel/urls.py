from django.urls import path
from . import views

app_name = 'admin_panel'

urlpatterns = [
    path('', views.admin_dashboard_view, name='dashboard'),
    path('users/', views.admin_users_view, name='users'),
    path('users/export/', views.export_all_users_csv, name='export_all_users'),
    path('users/<int:pk>/', views.admin_user_detail_view, name='user_detail'),

    path('subscriptions/', views.admin_subscriptions_view, name='subscriptions'),
    path('subscriptions/<int:pk>/', views.admin_subscription_detail_view, name='subscription_detail'),
    path('subscriptions/<int:pk>/cancel/', views.admin_cancel_subscription_view, name='cancel_subscription'),
    path('payments/', views.admin_payments_view, name='payments'),
    path('invoices/', views.admin_invoices_view, name='invoices'),
    path('plans/', views.admin_plans_view, name='plans'),
    path('grant-subscription/', views.admin_grant_subscription_view, name='grant_subscription'),
    path('settings/', views.admin_settings_view, name='settings'),
    # The 'support_chat_real_time' might be redundant if the main view handles real-time aspects or if it was for a different feature.
    # For now, I'll keep the primary routes for listing chats and viewing a specific user chat.
    # If 'support_chat_real_time' was intended for a different purpose, it should be reviewed.
    # path('support/real-time/', views.admin_support_chat_view, name='support_chat_real_time'), # Kept for now, review if needed
    path('messages/', views.contact_messages_view, name='contact_messages'),
    path('messages/<int:pk>/', views.contact_message_detail_view, name='contact_message_detail'),
    path('newsletters/', views.newsletter_subscribers_view, name='newsletter_subscribers'),
    path('newsletters/export/', views.export_newsletter_subscribers, name='export_newsletter_subscribers'),
    path('api/unread-messages/', views.unread_messages_api, name='unread_messages_api'),
    path('whatsapp-sessions/', views.admin_whatsapp_sessions_view, name='whatsapp_sessions'),
    path('whatsapp-sessions/<int:session_id>/disconnect/', views.admin_disconnect_session, name='disconnect_whatsapp_session'),
    path('whatsapp-sessions/<int:session_id>/delete/', views.admin_delete_session, name='delete_whatsapp_session'),
    path('logout/', views.admin_logout_view, name='logout'),
]
