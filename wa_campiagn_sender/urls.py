# wa_campiagn_sender/urls.py - Main URL configuration with error handlers

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.sitemaps.views import sitemap
from sitevisitor import api_views
from sitevisitor.sitemaps import StaticViewSitemap, BlogSitemap
from django.views.generic import TemplateView

# Global error handlers - apply to all apps
handler400 = 'sitevisitor.views.custom_400_view'
handler401 = 'sitevisitor.views.custom_401_view' 
handler403 = 'sitevisitor.views.custom_403_view'
handler404 = 'sitevisitor.views.custom_404_view'
handler429 = 'sitevisitor.views.custom_429_view'
handler500 = 'sitevisitor.views.custom_500_view'
handler503 = 'sitevisitor.views.custom_503_view'

# Sitemap configuration
sitemaps = {
    'static': StaticViewSitemap,
    'blogs': BlogSitemap,
}

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('sitevisitor.urls')),
    path('userpanel/', include('userpanel.urls')),
    path('adminpanel/', include('adminpanel.urls')),
    # Social Auth URLs
    path('social-auth/', include('social_django.urls', namespace='social')),
    # SEO URLs
    path('sitemap.xml', sitemap, {'sitemaps': sitemaps}, name='django.contrib.sitemaps.views.sitemap'),
    path('.well-known/security.txt', TemplateView.as_view(template_name='security.txt', content_type='text/plain')),
    path('security.txt', TemplateView.as_view(template_name='security.txt', content_type='text/plain')),
    # API endpoints - only include specific API views
    path('api/verify-license/', api_views.verify_license, name='api_verify_license'),
]

# Static and media files for development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)