from django.urls import path
from . import views

app_name = 'sitevisitor'

urlpatterns = [
    # Static pages (assuming these were already FBVs or simple views)
    path('', views.IndexView, name='home'),
    path('contact/', views.contact, name='contact'),
    path('blogs/', views.blogs, name='blogs'),
    path('blog/direct-whatsapp-outreach/', views.blog_post_direct_outreach, name='blog_post_direct_outreach'),
    path('blog/sending-bulk-whatsapp-safely/', views.blog_post_safe_sending, name='blog_post_safe_sending'),
    # New Blog Post URLs
    path('blog/smart-contact-management/', views.blog_post_contact_management, name='blog_post_contact_management'),
    path('blog/personalization-power-crafting-messages-that-convert/', views.blog_post_easy_personalization, name='blog_post_easy_personalization'),
    path('blog/event-marketing-invitations-reminders/', views.blog_post_event_marketing, name='blog_post_event_marketing'),
    path('blog/campaign-checklist-successful-whatsapp/', views.blog_post_campaign_checklist, name='blog_post_campaign_checklist'),
    path('blog/advanced-safety-avoiding-ban-hammer/', views.blog_post_advanced_safety, name='blog_post_advanced_safety'),
    path('blog/enterprise-whatsapp-solutions/', views.blog_post_extension_power, name='blog_post_extension_power'),
    path('blog/timing-frequency-maximizing-reach/', views.blog_post_timing_frequency, name='blog_post_timing_frequency'),

    path('privacy-policy/', views.PrivacyView, name='privacy'), 
    path('terms-of-service/', views.TermsView, name='terms'),       
    path('pricing/', views.PricingView, name='pricing'),
    path('refund/', views.RefundView, name='refund'),
    path('faqs/', views.FaqView, name='faqs'),
    path('about/', views.AboutView, name='about'),    

    # Authentication views (now FBVs)
    path('login/', views.login_view, name='login'),
    path('signup/', views.signup_view, name='signup'),
    path('verify-email/<str:token>/', views.email_verification_view, name='verify_email'),
    path('resend-verification/', views.resend_verification_view, name='resend_verification'),
    path('complete-social-signup/', views.complete_social_signup, name='complete_social_signup'),

    # Password reset URLs (now using custom FBVs)
    path('password-reset/', views.custom_password_reset_view, name='password_reset'),
    path('password-reset/done/', views.custom_password_reset_done_view, name='password_reset_done'),
    path('password-reset-confirm/<uidb64>/<token>/', views.custom_password_reset_confirm_view, name='password_reset_confirm'),
    path('password-reset-complete/', views.custom_password_reset_complete_view, name='password_reset_complete'),

    # E-commerce URLs
    path('buy/', views.buy_view, name='buy'),
    path('best-practices/', views.best_practices_view, name='best_practices'),
    path('newsletter-subscribe/', views.newsletter_subscribe, name='newsletter_subscribe'),
    
    # SEO URLs
    path('robots.txt', views.robots_txt_view, name='robots_txt'),
    path('2d26036c3e584873a854dfa997544388.txt', views.indexnow_key_view, name='indexnow_key'),
    
    # Extension license verification removed - Users now access campaigns via dashboard
    
    # Error pages for specific scenarios
    path('error/bad-request/', views.custom_400_view, name='error_400'),
    path('error/unauthorized/', views.custom_401_view, name='error_401'),
    path('error/forbidden/', views.custom_403_view, name='error_403'),
    path('error/not-found/', views.custom_404_view, name='error_404'),
    path('error/rate-limit/', views.custom_429_view, name='error_429'),
    path('error/server-error/', views.custom_500_view, name='error_500'),
    path('error/maintenance/', views.custom_503_view, name='error_503'),
    path('error/email-service/', views.custom_email_error_view, name='error_email'),
]
