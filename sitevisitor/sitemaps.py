from django.contrib.sitemaps import Sitemap
from django.urls import reverse

class StaticViewSitemap(Sitemap):
    priority = 0.8
    changefreq = 'weekly'
    protocol = 'https'

    def items(self):
        return [
            ('sitevisitor:home', 1.0, 'daily'),
            ('sitevisitor:about', 0.8, 'monthly'), 
            ('sitevisitor:contact', 0.7, 'monthly'),
            ('sitevisitor:privacy', 0.5, 'yearly'),
            ('sitevisitor:terms', 0.5, 'yearly'),
            ('sitevisitor:refund', 0.5, 'yearly'),
            ('sitevisitor:faqs', 0.8, 'weekly'),
            ('sitevisitor:blogs', 0.9, 'daily'),
            ('sitevisitor:best_practices', 0.9, 'weekly'),
            ('sitevisitor:pricing', 0.9, 'weekly'),
            ('sitevisitor:buy', 0.9, 'weekly'),
        ]

    def location(self, item):
        return reverse(item[0])
        
    def priority(self, item):
        return item[1]
        
    def changefreq(self, item):
        return item[2]

class BlogSitemap(Sitemap):
    changefreq = 'weekly'
    priority = 0.7
    protocol = 'https'

    def items(self):
        # Static blog posts since we don't have a Blog model
        return [
            'sitevisitor:blog_post_direct_outreach',
            'sitevisitor:blog_post_safe_sending',
            'sitevisitor:blog_post_contact_management',
            'sitevisitor:blog_post_easy_personalization',
            'sitevisitor:blog_post_event_marketing',
            'sitevisitor:blog_post_campaign_checklist',
            'sitevisitor:blog_post_advanced_safety',
            'sitevisitor:blog_post_extension_power',
            'sitevisitor:blog_post_timing_frequency',
        ]

    def location(self, item):
        return reverse(item)