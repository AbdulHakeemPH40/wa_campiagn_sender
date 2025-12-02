from django.conf import settings

def seo_context(request):
    """Add SEO-related context variables"""
    return {
        'site_url': getattr(settings, 'SITE_URL', 'https://wacampaignsender.com'),
        'site_domain': getattr(settings, 'SITE_DOMAIN', 'wacampaignsender.com'),
    }