from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from django.utils import timezone
from datetime import datetime

class StaticViewSitemap(Sitemap):
    """
    Sitemap for static pages with SEO optimization
    """
    priority = 0.8
    changefreq = 'weekly'
    protocol = 'https'

    def items(self):
        return [
            'sitevisitor:home',
            'sitevisitor:pricing', 
            'sitevisitor:about',
            'sitevisitor:contact',
            'sitevisitor:faqs',
            'sitevisitor:blogs',
            'sitevisitor:best_practices',
            'sitevisitor:terms',
            'sitevisitor:privacy',
            'sitevisitor:refund',
        ]

    def location(self, item):
        return reverse(item)
    
    def lastmod(self, item):
        # Return current date for dynamic content, specific dates for static content
        if item in ['sitevisitor:pricing', 'sitevisitor:home']:
            return timezone.now().date()
        return datetime(2025, 1, 25).date()
    
    def priority(self, item):
        # Set different priorities based on page importance
        priorities = {
            'sitevisitor:home': 1.0,
            'sitevisitor:pricing': 0.9,
            'sitevisitor:about': 0.7,
            'sitevisitor:contact': 0.7,
            'sitevisitor:faqs': 0.8,
            'sitevisitor:blogs': 0.8,
            'sitevisitor:best_practices': 0.8,
        }
        return priorities.get(item, 0.6)
    
    def changefreq(self, item):
        # Set different change frequencies based on content type
        frequencies = {
            'sitevisitor:home': 'daily',
            'sitevisitor:pricing': 'weekly',
            'sitevisitor:blogs': 'weekly',
            'sitevisitor:faqs': 'monthly',
        }
        return frequencies.get(item, 'monthly')

class BlogSitemap(Sitemap):
    """
    Sitemap for blog posts (when blog functionality is added)
    """
    changefreq = 'monthly'
    priority = 0.7
    protocol = 'https'

    def items(self):
        # This would return blog post objects when blog is implemented
        # For now, return empty list
        return []

    def lastmod(self, obj):
        # Return the last modified date of the blog post
        return timezone.now().date()

    def location(self, obj):
        # Return the URL of the blog post
        return f"/blog/{obj.slug}/"

# Sitemap index configuration
sitemaps = {
    'static': StaticViewSitemap,
    'blog': BlogSitemap,
}