import requests
import json
from django.conf import settings
from django.urls import reverse
import logging

logger = logging.getLogger(__name__)

def _brief_error_text(resp, max_len: int = 300) -> str:
    """Return sanitized/truncated error response text for logging."""
    if not resp:
        return "(no response)"
    try:
        ct = resp.headers.get('Content-Type', '')
    except Exception:
        ct = ''
    try:
        t = resp.text or ''
    except Exception:
        t = ''
    # Prefer concise JSON message/error
    try:
        data = resp.json()
        for key in ('message', 'error', 'details', 'detail'):
            val = data.get(key)
            if isinstance(val, str) and val:
                return val if len(val) <= max_len else (val[:max_len] + "…")
    except Exception:
        pass
    # Suppress HTML bodies
    if ('text/html' in ct) or ('<!DOCTYPE html' in t) or ('<html' in t):
        status = getattr(resp, 'status_code', None)
        status_info = f" (status {status})" if status is not None else ''
        return f"HTML body omitted{status_info}"
    # Truncate long text
    if len(t) > max_len:
        return t[:max_len] + "…"
    return t or "(empty body)"

class PayPalAPI:
    def __init__(self):
        self.client_id = settings.PAYPAL_CLIENT_ID
        self.client_secret = settings.PAYPAL_CLIENT_SECRET
        self.mode = settings.PAYPAL_MODE
        
        if self.mode == 'sandbox':
            self.base_url = 'https://api.sandbox.paypal.com'
        else:
            self.base_url = 'https://api.paypal.com'
    
    def validate_production_credentials(self):
        """Validate that production mode doesn't use sandbox credentials"""
        if self.mode == 'live':
            # Check if using sandbox client ID (sandbox IDs typically contain 'sandbox' or start with 'sb-')
            if ('sandbox' in self.client_id.lower() or 
                self.client_id.startswith('sb-') or 
                'test' in self.client_id.lower()):
                logger.error("SECURITY ERROR: Sandbox credentials detected in production mode!")
                return False
                
            # Check if using sandbox secret
            if ('sandbox' in self.client_secret.lower() or 
                'test' in self.client_secret.lower()):
                logger.error("SECURITY ERROR: Sandbox secret detected in production mode!")
                return False
                
        return True
    
    def get_access_token(self):
        """Get PayPal access token with production validation"""
        # Debug log credentials (first 10 chars only)
        logger.info(f"PayPal mode: {self.mode}")
        logger.info(f"PayPal client ID: {self.client_id[:10]}...")
        logger.info(f"PayPal base URL: {self.base_url}")
        
        # Validate credentials for production
        if not self.validate_production_credentials():
            logger.error("PayPal credential validation failed - blocking request")
            return None
            
        url = f"{self.base_url}/v1/oauth2/token"
        
        headers = {
            'Accept': 'application/json',
            'Accept-Language': 'en_US',
        }
        
        data = 'grant_type=client_credentials'
        
        try:
            response = requests.post(
                url,
                headers=headers,
                data=data,
                auth=(self.client_id, self.client_secret),
                timeout=10  # Reduced timeout
            )
            logger.info(f"PayPal token request status: {response.status_code}")
            response.raise_for_status()
            token_data = response.json()
            logger.info(f"PayPal token obtained successfully in {self.mode} mode")
            return token_data['access_token']
        except requests.exceptions.RequestException as e:
            logger.error(f"PayPal access token request error: {e}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"PayPal response: {_brief_error_text(e.response)}")
                # Check if error is due to sandbox credentials in production
                if self.mode == 'live' and 'invalid_client' in str(e.response.text).lower():
                    logger.error("POSSIBLE CAUSE: Sandbox credentials used in production mode")
            return None
        except Exception as e:
            logger.error(f"PayPal access token error: {e}")
            return None
    
    def get_order_details(self, order_id):
        """Get PayPal order details for verification"""
        access_token = self.get_access_token()
        if not access_token:
            logger.error("Failed to get PayPal access token for order verification")
            return None
        
        url = f"{self.base_url}/v2/checkout/orders/{order_id}"
        
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {access_token}',
        }
        
        try:
            response = requests.get(url, headers=headers, timeout=10)
            logger.info(f"PayPal order details request status: {response.status_code}")
            response.raise_for_status()
            order_data = response.json()
            logger.info(f"PayPal order details retrieved successfully for order: {order_id}")
            return order_data
        except requests.exceptions.RequestException as e:
            logger.error(f"PayPal order details request error: {e}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"PayPal response: {_brief_error_text(e.response)}")
            return None
        except Exception as e:
            logger.error(f"PayPal order details error: {e}")
            return None
    
    def verify_payment_capture(self, capture_id):
        """Verify PayPal payment capture for security"""
        access_token = self.get_access_token()
        if not access_token:
            logger.error("Failed to get PayPal access token for capture verification")
            return None
        
        url = f"{self.base_url}/v2/payments/captures/{capture_id}"
        
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {access_token}',
        }
        
        try:
            response = requests.get(url, headers=headers, timeout=10)
            logger.info(f"PayPal capture verification request status: {response.status_code}")
            response.raise_for_status()
            capture_data = response.json()
            logger.info(f"PayPal capture verified successfully: {capture_id}")
            return capture_data
        except requests.exceptions.RequestException as e:
            logger.error(f"PayPal capture verification request error: {e}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"PayPal response: {_brief_error_text(e.response)}")
            return None
        except Exception as e:
            logger.error(f"PayPal capture verification error: {e}")
            return None
    
    def create_payment(self, amount, description, currency='USD', return_url=None, cancel_url=None):
        """Create PayPal payment"""
        access_token = self.get_access_token()
        if not access_token:
            logger.error("Failed to get PayPal access token")
            return None
        
        url = f"{self.base_url}/v1/payments/payment"
        
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {access_token}',
        }
        
        payment_data = {
            "intent": "sale",
            "payer": {
                "payment_method": "paypal"
            },
            "redirect_urls": {
                "return_url": return_url or settings.PAYPAL_RETURN_URL,
                "cancel_url": cancel_url or settings.PAYPAL_CANCEL_URL
            },
            "application_context": {
                "brand_name": "WA Campaign Sender",
                "landing_page": "Billing",
                "user_action": "commit"
            },
            "transactions": [{
                "item_list": {
                    "items": [{
                        "name": description,
                        "sku": "subscription",
                        "price": str(amount),
                        "currency": currency,
                        "quantity": 1
                    }]
                },
                "amount": {
                    "currency": currency,
                    "total": str(amount)
                },
                "description": description
            }]
        }
        
        try:
            logger.info(f"Creating PayPal payment for ${amount}")
            response = requests.post(
                url, 
                headers=headers, 
                data=json.dumps(payment_data),
                timeout=30
            )
            logger.info(f"PayPal payment creation status: {response.status_code}")
            response.raise_for_status()
            payment_response = response.json()
            logger.info(f"PayPal payment created: {payment_response.get('id')}")
            return payment_response
        except requests.exceptions.RequestException as e:
            logger.error(f"PayPal create payment request error: {e}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"PayPal response status: {e.response.status_code}")
                logger.error(f"PayPal response text: {_brief_error_text(e.response)}")
                try:
                    error_json = e.response.json()
                    logger.error(f"PayPal error details: {error_json}")
                    # Log specific error for debugging
                    if 'details' in error_json:
                        for detail in error_json['details']:
                            logger.error(f"PayPal validation error: {detail}")
                except:
                    pass
            return None
        except Exception as e:
            logger.error(f"PayPal create payment error: {e}")
            return None
    
    def create_order_v2(self, amount, currency='USD', description='WA Campaign Sender Subscription'):
        """Create PayPal order using v2 API for better guest checkout support"""
        access_token = self.get_access_token()
        if not access_token:
            logger.error("Failed to get PayPal access token")
            return None
        
        url = f"{self.base_url}/v2/checkout/orders"
        
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {access_token}',
        }
        
        order_data = {
            "intent": "CAPTURE",
            "purchase_units": [{
                "amount": {
                    "currency_code": currency,
                    "value": str(amount)
                },
                "description": description
            }],
            "application_context": {
                "brand_name": "WA Campaign Sender",
                "landing_page": "BILLING",  # Show credit card form first
                "user_action": "PAY_NOW",    # Show "Pay Now" instead of "Continue"
                "shipping_preference": "NO_SHIPPING",  # Digital product
                "payment_method": {
                    "payee_preferred": "UNRESTRICTED",  # Allow guest checkout
                    "payer_selected": "PAYPAL"  # Default but allow cards
                },
                "return_url": settings.PAYPAL_RETURN_URL,
                "cancel_url": settings.PAYPAL_CANCEL_URL
            }
        }
        
        try:
            logger.info(f"Creating PayPal v2 order for ${amount}")
            response = requests.post(
                url, 
                headers=headers, 
                data=json.dumps(order_data),
                timeout=30
            )
            logger.info(f"PayPal v2 order creation status: {response.status_code}")
            response.raise_for_status()
            order_response = response.json()
            logger.info(f"PayPal v2 order created: {order_response.get('id')}")
            return order_response
        except requests.exceptions.RequestException as e:
            logger.error(f"PayPal v2 create order request error: {e}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"PayPal response status: {e.response.status_code}")
                logger.error(f"PayPal response text: {_brief_error_text(e.response)}")
                try:
                    error_json = e.response.json()
                    logger.error(f"PayPal error details: {error_json}")
                except:
                    pass
            return None
        except Exception as e:
            logger.error(f"PayPal v2 create order error: {e}")
            return None
    
    def capture_order_v2(self, order_id):
        """Capture PayPal order using v2 API"""
        access_token = self.get_access_token()
        if not access_token:
            logger.error("Failed to get PayPal access token")
            return None
        
        url = f"{self.base_url}/v2/checkout/orders/{order_id}/capture"
        
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {access_token}',
        }
        
        try:
            logger.info(f"Capturing PayPal v2 order: {order_id}")
            response = requests.post(url, headers=headers, timeout=30)
            logger.info(f"PayPal v2 capture status: {response.status_code}")
            response.raise_for_status()
            capture_response = response.json()
            logger.info(f"PayPal v2 order captured: {capture_response.get('status')}")
            return capture_response
        except requests.exceptions.RequestException as e:
            logger.error(f"PayPal v2 capture order request error: {e}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"PayPal response status: {e.response.status_code}")
                logger.error(f"PayPal response text: {_brief_error_text(e.response)}")
                try:
                    error_json = e.response.json()
                    logger.error(f"PayPal error details: {error_json}")
                except:
                    pass
            return None
        except Exception as e:
            logger.error(f"PayPal v2 capture order error: {e}")
            return None

    def execute_payment(self, payment_id, payer_id):
        """Execute PayPal payment"""
        access_token = self.get_access_token()
        if not access_token:
            return None
        
        url = f"{self.base_url}/v1/payments/payment/{payment_id}/execute"
        
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {access_token}',
        }
        
        execute_data = {
            "payer_id": payer_id
        }
        
        try:
            response = requests.post(url, headers=headers, data=json.dumps(execute_data))
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"PayPal execute payment error: {e}")
            return None
    
    def get_payment_details(self, payment_id):
        """Get PayPal payment details"""
        access_token = self.get_access_token()
        if not access_token:
            return None
        
        url = f"{self.base_url}/v1/payments/payment/{payment_id}"
        
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {access_token}',
        }
        
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"PayPal get payment details error: {e}")
            return None