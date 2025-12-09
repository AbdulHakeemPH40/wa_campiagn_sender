from django.urls import path
from . import views

app_name = 'whatsappapi'

urlpatterns = [
    # Dashboard
    path('', views.dashboard, name='dashboard'),
    
    # Campaign Management
    path('send-campaign/', views.send_campaign, name='send_campaign'),
    path('ai-draft/', views.ai_draft, name='ai_draft'),
    path('send-test-message/', views.send_test_message, name='send_test_message'),
    path('campaigns/', views.campaign_list, name='campaigns'),
    path('campaigns/<int:campaign_id>/', views.campaign_detail, name='campaign_detail'),
    path('campaigns/<int:campaign_id>/stats/', views.campaign_stats_api, name='campaign_stats_api'),
    path('campaigns/<int:campaign_id>/retry-failed/', views.retry_failed_messages, name='retry_failed_messages'),
    path('campaigns/<int:campaign_id>/retry-single/', views.retry_single_recipient, name='retry_single_recipient'),
    path('campaigns/<int:campaign_id>/stop/', views.stop_campaign, name='stop_campaign'),
    path('campaigns/<int:campaign_id>/export/excel/', views.export_campaign_messages_excel, name='export_campaign_messages_excel'),
    
    # Contacts Management
    path('contacts/', views.contacts, name='contacts'),
    path('contacts/upload/', views.upload_contacts, name='upload_contacts'),
    path('contacts/<int:list_id>/rename/', views.rename_contact_list, name='rename_contact_list'),
    path('contacts/<int:list_id>/delete/', views.delete_contact_list, name='delete_contact_list'),
    path('contacts/<int:list_id>/export/csv/', views.export_contact_list_csv, name='export_contact_list_csv'),
    path('contacts/<int:list_id>/export/excel/', views.export_contact_list_excel, name='export_contact_list_excel'),
    path('contacts/sample-csv/', views.download_sample_csv, name='download_sample_csv'),
    path('contacts/sample-excel/', views.download_sample_excel, name='download_sample_excel'),
    
    # Opt-Out Management
    path('optout/<int:optout_id>/remove/', views.remove_optout, name='remove_optout'),
    path('optout/export/csv/', views.export_optout_csv, name='export_optout_csv'),
    path('optout/export/excel/', views.export_optout_excel, name='export_optout_excel'),
    
    # API Endpoints
    path('api/contact-list-fields/<int:list_id>/', views.get_contact_list_fields, name='get_contact_list_fields'),
    path('api/contact-lists/', views.api_contact_lists, name='api_contact_lists'),
    path('api/check-moderation/', views.check_moderation, name='check_moderation'),
    
    # Session Management  
    path('sessions/', views.sessions_list, name='sessions'),
    path('create-session/', views.create_session, name='create_session'),
    path('connect/<int:session_id>/', views.connect_session, name='connect_session'),
    path('session/<int:session_id>/status/', views.check_session_status, name='check_session_status'),
    path('session/<int:session_id>/disconnect/', views.disconnect_session, name='disconnect_session'),
    path('session/<int:session_id>/delete/', views.delete_session, name='delete_session'),
    path('refresh-sessions/', views.refresh_all_sessions, name='refresh_all_sessions'),
    
    # Webhook
    path('webhook/<int:user_id>/', views.wasender_webhook, name='wasender_webhook'),
    path('update-webhooks/', views.update_all_webhooks, name='update_all_webhooks'),
    
    # Draft Templates
    path('drafts/', views.drafts_list, name='drafts'),
    path('drafts/save/', views.save_draft, name='save_draft'),
    path('drafts/<int:draft_id>/', views.get_draft, name='get_draft'),
    path('drafts/<int:draft_id>/delete/', views.delete_draft, name='delete_draft'),
]

