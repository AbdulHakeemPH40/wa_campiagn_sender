import requests
import json
import logging
from django.conf import settings
from django.urls import reverse
from typing import List, Optional

logger = logging.getLogger(__name__)

def _brief_response_text(response, max_len: int = 300) -> str:
    """Return sanitized/truncated response body for logging."""
    try:
        ct = response.headers.get('Content-Type', '')
    except Exception:
        ct = ''
    try:
        t = response.text or ''
    except Exception:
        t = ''
    # Prefer concise JSON message/error
    try:
        data = response.json()
        for key in ('message', 'error', 'detail'):
            val = data.get(key)
            if isinstance(val, str) and val:
                return val if len(val) <= max_len else (val[:max_len] + "…")
    except Exception:
        pass
    if ('text/html' in ct) or ('<!DOCTYPE html' in t) or ('<html' in t):
        status = getattr(response, 'status_code', None)
        status_info = f" (status {status})" if status is not None else ''
        return f"HTML body omitted{status_info}"
    if len(t) > max_len:
        return t[:max_len] + "…"
    return t or "(empty body)"

class IndexNowSubmitter:
    """
    IndexNow API implementation for instant search engine notification
    """
    
    def __init__(self):
        # Bing IndexNow API key from Bing Webmaster Tools
        self.api_key = "2d26036c3e584873a854dfa997544388"
        self.host = "wacampaignsender.com"
        self.indexnow_endpoint = "https://api.indexnow.org/indexnow"
        
    def submit_urls(self, urls: List[str]) -> bool:
        """
        Submit URLs to IndexNow API
        
        Args:
            urls: List of full URLs to submit
            
        Returns:
            bool: True if successful, False otherwise
        """
        if not urls:
            return False
            
        payload = {
            "host": self.host,
            "key": self.api_key,
            "keyLocation": f"https://{self.host}/{self.api_key}.txt",
            "urlList": urls
        }
        
        try:
            response = requests.post(
                self.indexnow_endpoint,
                json=payload,
                headers={
                    "Content-Type": "application/json; charset=utf-8"
                },
                timeout=30
            )
            
            if response.status_code == 200:
                logger.info(f"Successfully submitted {len(urls)} URLs to IndexNow")
                return True
            else:
                logger.error(f"IndexNow submission failed: {response.status_code} - {_brief_response_text(response)}")
                return False
                
        except requests.exceptions.RequestException as e:
            logger.error(f"IndexNow submission error: {str(e)}")
            return False
    
    def submit_single_url(self, url: str) -> bool:
        """
        Submit a single URL to IndexNow
        
        Args:
            url: Full URL to submit
            
        Returns:
            bool: True if successful, False otherwise
        """
        return self.submit_urls([url])
    
    def submit_page_update(self, page_path: str) -> bool:
        """
        Submit a page update notification
        
        Args:
            page_path: Relative path of the updated page (e.g., '/pricing/')
            
        Returns:
            bool: True if successful, False otherwise
        """
        full_url = f"https://{self.host}{page_path}"
        return self.submit_single_url(full_url)

# Convenience functions for common use cases
def notify_page_update(page_path: str) -> bool:
    """
    Notify search engines about a page update
    
    Args:
        page_path: Relative path of the updated page
        
    Returns:
        bool: True if successful, False otherwise
    """
    submitter = IndexNowSubmitter()
    return submitter.submit_page_update(page_path)

def notify_new_blog_post(post_slug: str) -> bool:
    """
    Notify search engines about a new blog post
    
    Args:
        post_slug: Slug of the new blog post
        
    Returns:
        bool: True if successful, False otherwise
    """
    page_path = f"/blog/{post_slug}/"
    return notify_page_update(page_path)

def notify_pricing_update() -> bool:
    """
    Notify search engines about pricing page updates
    
    Returns:
        bool: True if successful, False otherwise
    """
    return notify_page_update("/pricing/")

def notify_multiple_pages(page_paths: List[str]) -> bool:
    """
    Notify search engines about multiple page updates
    
    Args:
        page_paths: List of relative page paths
        
    Returns:
        bool: True if successful, False otherwise
    """
    submitter = IndexNowSubmitter()
    full_urls = [f"https://{submitter.host}{path}" for path in page_paths]
    return submitter.submit_urls(full_urls)