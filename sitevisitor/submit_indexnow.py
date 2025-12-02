#!/usr/bin/env python
"""
Script to submit all important URLs to IndexNow for immediate Bing indexing
Run with: python manage.py shell < sitevisitor/submit_indexnow.py
"""

from sitevisitor.indexnow import IndexNowSubmitter

def submit_all_urls():
    submitter = IndexNowSubmitter()
    
    # All important URLs for your site
    urls = [
        "https://wacampaignsender.com/",
        "https://wacampaignsender.com/pricing/",
        "https://wacampaignsender.com/about/",
        "https://wacampaignsender.com/contact/",
        "https://wacampaignsender.com/privacy-policy/",
        "https://wacampaignsender.com/terms-of-service/",
        "https://wacampaignsender.com/signup/",
        "https://wacampaignsender.com/login/",
    ]
    
    print("Submitting URLs to IndexNow...")
    
    if submitter.submit_urls(urls):
        print(f'Successfully submitted {len(urls)} URLs to IndexNow')
    else:
        print('Failed to submit URLs to IndexNow')

# Run the function
submit_all_urls()