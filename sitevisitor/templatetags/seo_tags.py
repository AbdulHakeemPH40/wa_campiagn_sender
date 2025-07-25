from django import template
from django.utils.safestring import mark_safe
import json

register = template.Library()

@register.simple_tag
def json_ld(data):
    """Convert Python dict to JSON-LD structured data"""
    return mark_safe(json.dumps(data, indent=2))

@register.simple_tag
def breadcrumb_json_ld(breadcrumbs):
    """Generate breadcrumb JSON-LD structured data"""
    items = []
    for i, (name, url) in enumerate(breadcrumbs, 1):
        items.append({
            "@type": "ListItem",
            "position": i,
            "name": name,
            "item": url
        })
    
    data = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": items
    }
    
    return mark_safe(json.dumps(data, indent=2))