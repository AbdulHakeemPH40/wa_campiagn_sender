import requests
import json
from django.conf import settings
from django.urls import reverse
import logging

logger = logging.getLogger(__name__)

class PayPalAPI:
    def __init__(self):
        self.client_id = settings.PAYPAL_CLIENT_ID
        self.client_secret = settings.PAYPAL_CLIENT_SECRET
        self.mode = settings.PAYPAL_MODE
        
        if self.mode == 'sandbox':
            self.base_url = 'https://api.sandbox.paypal.com'
        else:
            self.base_url = 'https://api.paypal.com'
    
    def get_access_token(self):
        """Get PayPal access token"""
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
                timeout=30
            )
            logger.info(f"PayPal token request status: {response.status_code}")
            response.raise_for_status()
            token_data = response.json()
            logger.info(f"PayPal token obtained successfully")
            return token_data['access_token']
        except requests.exceptions.RequestException as e:
            logger.error(f"PayPal access token request error: {e}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"PayPal response: {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"PayPal access token error: {e}")
            return None
    
    def create_payment(self, amount, currency='USD', description='WA Campaign Sender Subscription'):
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
                "return_url": settings.PAYPAL_RETURN_URL,
                "cancel_url": settings.PAYPAL_CANCEL_URL
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
                logger.error(f"PayPal response: {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"PayPal create payment error: {e}")
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