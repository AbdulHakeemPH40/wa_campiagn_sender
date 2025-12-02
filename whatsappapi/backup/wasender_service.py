"""
WASender API Service
Handles all interactions with WASender Partner Program API
Documentation: https://wasenderapi.com/api-docs
"""

import requests
import logging
import base64
import io
from django.conf import settings
from django.utils import timezone
from cryptography.fernet import Fernet
import qrcode
from PIL import Image
from .models import WASenderSession, WASenderMessage, WASenderIncomingMessage

logger = logging.getLogger(__name__)


# Helper to avoid dumping raw HTML or oversized bodies into logs
def _brief_response_text(response, max_len: int = 300) -> str:
    """Return a short, sanitized summary of an HTTP response body for logging.
    - Prefer JSON 'message'/'error' fields when available
    - Detect and suppress HTML pages (e.g., Cloudflare error pages)
    - Truncate long bodies
    """
    try:
        content_type = response.headers.get('Content-Type', '')
    except Exception:
        content_type = ''
    try:
        text = response.text or ''
    except Exception:
        text = ''

    # Prefer concise JSON message/error/detail
    try:
        data = response.json()
        for key in ('message', 'error', 'detail'):
            val = data.get(key)
            if isinstance(val, str) and val:
                return val if len(val) <= max_len else (val[:max_len] + "…")
    except Exception:
        pass

    # Sanitize HTML error pages
    if ('text/html' in content_type) or ('<!DOCTYPE html' in text) or ('<html' in text):
        import re
        ray_match = re.search(r'Cloudflare Ray ID:\s*([A-Za-z0-9]+)', text)
        ray_info = f" (Ray ID {ray_match.group(1)})" if ray_match else ''
        status = getattr(response, 'status_code', None)
        status_info = f" (status {status})" if status is not None else ''
        return f"HTML error page{ray_info}{status_info}"

    # Truncate overly long bodies
    if len(text) > max_len:
        return text[:max_len] + "…"
    return text or "(empty body)"


class WASenderService:
    """
    Service class for WASender API integration.
    Handles session management, message sending, and webhook processing.
    Based on official docs: https://wasenderapi.com/api-docs
    """
    
    BASE_URL = "https://www.wasenderapi.com/api"
    
    def __init__(self):
        # Personal Access Token (from settings page) - used for session management
        self.personal_access_token = getattr(settings, 'WASENDER_PERSONAL_ACCESS_TOKEN', '')
        self.encryption_key = getattr(settings, 'ENCRYPTION_KEY', Fernet.generate_key())
        
        # Debug: Log token status
        if self.personal_access_token:
            logger.info(f"WASender API token loaded: {self.personal_access_token[:20]}...")
        else:
            logger.error("WASender API token NOT FOUND in settings!")
    
    def _get_headers(self, token=None):
        """Get API request headers with authentication"""
        return {
            "Authorization": f"Bearer {token or self.personal_access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
    
    def _encrypt_token(self, token):
        """Encrypt API token for secure storage"""
        try:
            cipher = Fernet(self.encryption_key)
            return cipher.encrypt(token.encode()).decode()
        except Exception as e:
            logger.error(f"Token encryption error: {e}")
            return token  # Fallback to plain text (not recommended for production)
    
    def _decrypt_token(self, encrypted_token):
        """Decrypt stored API token with fallback for unencrypted tokens"""
        if not encrypted_token:
            return ''
        
        try:
            cipher = Fernet(self.encryption_key)
            return cipher.decrypt(encrypted_token.encode()).decode()
        except Exception as e:
            # If decryption fails, token might be plain text or encrypted with old key
            # Return as-is and let API validation handle it
            logger.warning(f"Token decryption failed, using token as-is: {str(e)[:50]}")
            return encrypted_token

    # ==================== Helpers: Phone & Checks ====================
    def _format_phone_number(self, phone_number):
        """
        Convert input to E.164-like format: keep digits, ensure leading '+'.
        """
        if not phone_number:
            return ''
        s = str(phone_number).strip()
        # Remove common formatting
        for ch in [' ', '-', '(', ')']:
            s = s.replace(ch, '')
        # Handle 00 prefix as international
        if s.startswith('00'):
            s = '+' + s[2:]
        # Keep only digits after optional leading plus
        if s.startswith('+'):
            digits = ''.join(c for c in s[1:] if c.isdigit())
            s = '+' + digits
        else:
            digits = ''.join(c for c in s if c.isdigit())
            s = '+' + digits
        return s

    def _is_valid_e164(self, number):
        """Basic E.164 validation: + followed by 7–15 digits, no leading zero."""
        import re
        return bool(re.match(r'^\+[1-9]\d{6,14}$', str(number or '')))

    def check_whatsapp(self, session, phone_number):
        """
        Check if a phone number is registered on WhatsApp.
        Returns {'exists': bool, 'jid': str|None, 'ok': bool, 'error': str|None}
        """
        try:
            session_api_key = self._decrypt_token(session.api_token)
            response = requests.get(
                f"{self.BASE_URL}/check-whatsapp",
                params={'phone': phone_number},
                headers=self._get_headers(session_api_key),
                timeout=30
            )
            # Handle rate limit by waiting and retrying once
            if response.status_code == 429:
                import time, json as _json
                try:
                    rate_data = response.json()
                except Exception:
                    try:
                        rate_data = _json.loads(response.text)
                    except Exception:
                        rate_data = {}
                retry_after = int(rate_data.get('retry_after', 5))
                logger.warning(f"Rate limited on check-whatsapp: waiting {retry_after}s before retrying")
                time.sleep(retry_after)
                response = requests.get(
                    f"{self.BASE_URL}/check-whatsapp",
                    params={'phone': phone_number},
                    headers=self._get_headers(session_api_key),
                    timeout=30
                )
            if response.status_code == 200:
                data = response.json()
                result = data.get('data', {})
                exists = result.get('exists')
                if exists is None:
                    exists = bool(result.get('jid'))
                result['exists'] = bool(exists)
                result['ok'] = True
                logger.info(f"WhatsApp check for {phone_number}: {result}")
                return result
            else:
                logger.error(f"Failed to check WhatsApp: {response.status_code} - {_brief_response_text(response)}")
                return {'exists': False, 'ok': False, 'error': _brief_response_text(response)}
        except Exception as e:
            logger.error(f"Error checking WhatsApp: {e}")
            return {'exists': False, 'ok': False, 'error': str(e)}
    
    # ==================== Session Management ====================
    
    def list_sessions(self):
        """
        List all WhatsApp sessions from WASender
        GET /api/whatsapp-sessions
        
        Returns:
            list of session data or None
        """
        try:
            response = requests.get(
                f"{self.BASE_URL}/whatsapp-sessions",
                headers=self._get_headers(),
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                return data.get('data', [])
            else:
                logger.error(f"Failed to list sessions: {response.status_code} - {_brief_response_text(response)}")
                return None
                
        except Exception as e:
            logger.error(f"Error listing sessions: {e}")
            return None
    
    def create_session(self, user, webhook_url, phone_number):
        """
        Create new WhatsApp session for user
        POST /api/whatsapp-sessions
        
        Required parameters per WASender docs:
        - name: string (required)
        - phone_number: string (required) - User's actual WhatsApp number
        - account_protection: boolean (required)
        - log_messages: boolean (required)
        - webhook_url: string (optional)
        - webhook_enabled: boolean (optional)
        - webhook_events: array (optional)
        
        Args:
            user: Django User instance
            webhook_url: Webhook URL for this session
            phone_number: User's WhatsApp phone number (e.g., +1234567890)
        
        Returns:
            WASenderSession instance or None
        """
        session_name = f"user_{user.id}_{int(timezone.now().timestamp())}"
        
        # Skip webhook for localhost
        if 'localhost' in webhook_url or '127.0.0.1' in webhook_url:
            webhook_url = None
        
        payload = {
            "name": session_name,
            "phone_number": phone_number,  # User's actual phone
            "account_protection": True,
            "log_messages": True
        }
        
        # Add webhook only if public URL
        if webhook_url:
            payload["webhook_url"] = webhook_url
            payload["webhook_enabled"] = True
            payload["webhook_events"] = [
                "messages.received",
                "session.status",
                "messages.update"
            ]
            payload["read_incoming_messages"] = False
            payload["auto_reject_calls"] = False
        
        try:
            # Debug logging
            logger.info(f"Creating session with URL: {self.BASE_URL}/whatsapp-sessions")
            logger.info(f"Token (first 30 chars): {self.personal_access_token[:30]}...")
            logger.info(f"Headers: {self._get_headers()}")
            logger.info(f"Payload: {payload}")
            
            response = requests.post(
                f"{self.BASE_URL}/whatsapp-sessions",
                headers=self._get_headers(),
                json=payload,
                timeout=30
            )
            
            logger.info(f"Response status: {response.status_code}")
            logger.info(f"Response body: {_brief_response_text(response)}")
            
            if response.status_code in [200, 201]:
                data = response.json()
                session_data = data.get('data', data)  # Handle wrapped response
                
                # Extract session info
                session_id = session_data.get('id')
                api_key = session_data.get('api_key', '')
                
                # Create session in database
                session = WASenderSession.objects.create(
                    user=user,
                    session_id=str(session_id),
                    session_name=session_name,
                    api_token=self._encrypt_token(api_key),
                    phone_number=phone_number,  # Store initial phone number
                    webhook_url=webhook_url,
                    status='disconnected'  # Initial status
                )
                
                logger.info(f"Session created: {session.session_id} for user {user.email}")
                return session
            else:
                # Extract error message from WASender response
                try:
                    error_data = response.json()
                    error_msg = error_data.get('error', error_data.get('message', response.text))
                except:
                    error_msg = response.text
                
                logger.error(f"Failed to create session: {response.status_code} - {error_msg}")
                
                # Raise exception with actual error message for better error handling
                if response.status_code == 403:
                    raise Exception(f"Session limit reached: {error_msg}")
                elif response.status_code == 422:
                    raise Exception(f"Validation error: {error_msg}")
                else:
                    raise Exception(f"API Error ({response.status_code}): {error_msg}")
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error creating session: {e}")
            return None
        except Exception as e:
            logger.error(f"Error creating session: {e}")
            return None
    
    def connect_session(self, session):
        """
        Initiate connection process for a session
        POST /api/whatsapp-sessions/{whatsappSession}/connect
        
        Args:
            session: WASenderSession instance
        
        Returns:
            bool: True if connection initiated
        """
        try:
            url = f"{self.BASE_URL}/whatsapp-sessions/{session.session_id}/connect"
            logger.info(f"Connecting session at: {url}")
            
            response = requests.post(
                url,
                headers=self._get_headers(),
                timeout=30
            )
            
            logger.info(f"Connect response status: {response.status_code}")
            logger.info(f"Connect response: {_brief_response_text(response)}")
            
            if response.status_code in [200, 201]:
                # Update session status to pending
                session.status = 'pending'
                session.save()
                logger.info(f"Connection initiated for session {session.session_id}, status set to pending")
                return True
            else:
                logger.error(f"Failed to connect session: {response.status_code} - {_brief_response_text(response)}")
                return False
                
        except Exception as e:
            logger.error(f"Error connecting session: {e}")
            return False
    
    def get_qr_code(self, session):
        """
        Get QR code for WhatsApp connection
        GET /api/whatsapp-sessions/{whatsappSession}/qrcode
        
        Args:
            session: WASenderSession instance
        
        Returns:
            QR code data URL or None
        """
        try:
            url = f"{self.BASE_URL}/whatsapp-sessions/{session.session_id}/qrcode"
            logger.info(f"Fetching QR code from: {url}")
            
            response = requests.get(
                url,
                headers=self._get_headers(),
                timeout=30
            )
            
            logger.info(f"QR code response status: {response.status_code}")
            logger.info(f"QR code response: {_brief_response_text(response)}")
            
            if response.status_code == 200:
                data = response.json()
                logger.info(f"QR data keys: {data.keys()}")
                
                # QR code is in data.qrCode (camelCase!)
                qr_text = data.get('data', {}).get('qrCode') or data.get('qrCode')
                logger.info(f"QR text extracted: {qr_text[:100] if qr_text else 'None'}")
                
                if qr_text:
                    # Generate QR code image from text
                    import qrcode.constants
                    qr = qrcode.QRCode(
                        version=1,
                        error_correction=qrcode.constants.ERROR_CORRECT_L,
                        box_size=10,
                        border=4,
                    )
                    qr.add_data(qr_text)
                    qr.make(fit=True)
                    
                    # Create image
                    img = qr.make_image(fill_color="black", back_color="white")
                    
                    # Convert to base64 data URL
                    buffer = io.BytesIO()
                    img.save(buffer, 'PNG')
                    img_str = base64.b64encode(buffer.getvalue()).decode()
                    qr_code_url = f"data:image/png;base64,{img_str}"
                    
                    logger.info("QR code image generated successfully")
                    return qr_code_url
                
                return None
            else:
                logger.error(f"Failed to get QR code: {response.status_code} - {_brief_response_text(response)}")
                return None
                
        except Exception as e:
            logger.error(f"Error getting QR code: {e}")
            return None
    
    def get_session_status(self, session):
        """
        Check session connection status
        GET /api/whatsapp-sessions/{whatsappSession}
        Also GET /api/status for current status
        
        Args:
            session: WASenderSession instance
        
        Returns:
            dict with status info or None
        """
        try:
            # Get session details
            response = requests.get(
                f"{self.BASE_URL}/whatsapp-sessions/{session.session_id}",
                headers=self._get_headers(),
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                session_data = data.get('data', data)
                
                # Extract status info
                old_status = session.status
                new_status = session_data.get('status', 'disconnected')
                
                # Map WASender status to our status
                status_map = {
                    'connected': 'connected',
                    'open': 'connected',
                    'qr': 'pending',
                    'need_scan': 'pending',  # WASender uses 'need_scan'
                    'NEED_SCAN': 'pending',  # Uppercase variant
                    'disconnected': 'disconnected',
                    'logged_out': 'disconnected',  # Logged out = disconnected
                    'close': 'disconnected'
                }
                session.status = status_map.get(new_status, new_status)
                
                # Extract phone number if available (from WhatsApp after scanning)
                logger.info(f"Session data keys: {session_data.keys()}")
                logger.info(f"Full session data: {session_data}")
                
                # Check if there's nested phone info in session_data
                nested_session_data = session_data.get('session_data', {})
                if nested_session_data:
                    logger.info(f"Nested session_data: {nested_session_data}")
                    # Check for phone in nested data
                    if 'phone' in nested_session_data:
                        session.connected_phone_number = nested_session_data.get('phone')
                        logger.info(f"Found phone in nested session_data: {session.connected_phone_number}")
                    elif 'phoneNumber' in nested_session_data:
                        session.connected_phone_number = nested_session_data.get('phoneNumber')
                        logger.info(f"Found phoneNumber in nested session_data: {session.connected_phone_number}")
                
                # If still not found, check top-level fields
                if not session.connected_phone_number:
                    if 'phone' in session_data:
                        session.connected_phone_number = session_data.get('phone')
                        logger.info(f"Found phone in session_data: {session.connected_phone_number}")
                    elif 'phoneNumber' in session_data:
                        session.connected_phone_number = session_data.get('phoneNumber')
                        logger.info(f"Found phoneNumber in session_data: {session.connected_phone_number}")
                    elif 'phone_number' in session_data:
                        # This is the session creation number, not the scanned one
                        # Only use it if no other source found
                        session.connected_phone_number = session_data.get('phone_number')
                        logger.info(f"Using phone_number from session_data (may be original): {session.connected_phone_number}")
                    else:
                        logger.warning(f"Phone number not found in session_data")
                
                if session.status == 'connected' and old_status != 'connected':
                    session.connected_at = timezone.now()
                
                session.last_activity_at = timezone.now()
                session.save()
                
                # If connected, try to get actual WhatsApp user info
                if session.status == 'connected':
                    self._fetch_whatsapp_user_info(session)
                
                logger.info(f"Session {session.session_id} status: {session.status}")
                return session_data
            else:
                # Sanitize noisy HTML error pages (e.g., Cloudflare 5xx) and prefer concise messages
                try:
                    content_type = response.headers.get('Content-Type', '')
                except Exception:
                    content_type = ''
                error_text = response.text
                safe_log = None
                if ('text/html' in content_type) or ('<!DOCTYPE html' in str(error_text)):
                    import re
                    ray_match = re.search(r'Cloudflare Ray ID:\s*([A-Za-z0-9]+)', str(error_text))
                    ray_info = f" (Ray ID {ray_match.group(1)})" if ray_match else ''
                    safe_log = f"Failed to get status: {response.status_code} - HTML error page{ray_info}. Please retry later."
                else:
                    # Prefer JSON 'message' field if present
                    msg = None
                    try:
                        data = response.json()
                        msg = data.get('message')
                    except Exception:
                        msg = None
                    snippet = (msg or str(error_text))
                    # Truncate to prevent log flooding
                    if len(snippet) > 200:
                        snippet = snippet[:200] + '…'
                    safe_log = f"Failed to get status: {response.status_code} - {snippet}"
                logger.error(safe_log)
                return None
                
        except Exception as e:
            logger.error(f"Error getting session status: {e}")
            return None
    
    def _fetch_whatsapp_user_info(self, session):
        """
        Fetch actual WhatsApp user info (phone number) from connected session
        GET /api/user
        
        Args:
            session: WASenderSession instance
        """
        try:
            # Get session-specific API key
            session_api_key = self._decrypt_token(session.api_token)
            
            response = requests.get(
                f"{self.BASE_URL}/user",
                headers=self._get_headers(session_api_key),
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                user_data = data.get('data', data)
                
                logger.info(f"WhatsApp user data: {user_data}")
                
                # Extract actual connected phone number
                if 'id' in user_data:
                    # WhatsApp ID format: "{phone}@s.whatsapp.net" or "{phone}:{device_id}@s.whatsapp.net"
                    whatsapp_id = user_data.get('id', '')
                    if '@' in whatsapp_id:
                        phone = whatsapp_id.split('@')[0]
                        # Remove device ID suffix (e.g., :0, :1, :12)
                        if ':' in phone:
                            phone = phone.split(':')[0]
                        # Add + prefix
                        session.connected_phone_number = f"+{phone}"
                        session.save(update_fields=['connected_phone_number'])
                        logger.info(f"Updated connected_phone_number: {session.connected_phone_number}")
                elif 'phone' in user_data:
                    session.connected_phone_number = user_data.get('phone')
                    session.save(update_fields=['connected_phone_number'])
                    logger.info(f"Updated connected_phone_number: {session.connected_phone_number}")
            else:
            logger.warning(f"Failed to get user info: {response.status_code} - {_brief_response_text(response)}")
                
        except Exception as e:
            logger.error(f"Error fetching WhatsApp user info: {e}")
    
    def disconnect_session(self, session):
        """
        Disconnect WhatsApp session
        
        Args:
            session: WASenderSession instance
        
        Returns:
            bool: True if successful
        """
        try:
            url = f"{self.BASE_URL}/whatsapp-sessions/{session.session_id}/disconnect"
            logger.info(f"Disconnecting session at: {url}")
            
            response = requests.post(
                url,
                headers=self._get_headers(),
                timeout=30
            )
            
            logger.info(f"Disconnect response status: {response.status_code}")
            logger.info(f"Disconnect response: {_brief_response_text(response)}")
            
            if response.status_code in [200, 204]:
                session.status = 'disconnected'
                session.disconnected_at = timezone.now()
                session.save()
                logger.info(f"Session disconnected: {session.session_id}")
                return True
            else:
            logger.error(f"Failed to disconnect: {response.status_code} - {_brief_response_text(response)}")
                return False
                
        except Exception as e:
            logger.error(f"Error disconnecting session: {e}")
            return False
    
    def delete_session(self, session):
        """
        Delete WhatsApp session
        
        Args:
            session: WASenderSession instance
        
        Returns:
            bool: True if successful or session doesn't exist (404)
        """
        try:
            response = requests.delete(
                f"{self.BASE_URL}/whatsapp-sessions/{session.session_id}",
                headers=self._get_headers(),
                timeout=30
            )
            
            if response.status_code in [200, 204]:
                logger.info(f"Session deleted from WASender: {session.session_id}")
                return True
            elif response.status_code == 404:
                # Session doesn't exist on WASender - that's okay, we'll delete locally
                logger.info(f"Session not found on WASender (404): {session.session_id} - will delete locally")
                return True
            else:
            logger.error(f"Failed to delete: {response.status_code} - {_brief_response_text(response)}")
                return False
                
        except Exception as e:
            logger.error(f"Error deleting session: {e}")
            return False
    
    # ==================== Message Sending ====================
    
    def send_text_message(self, session, recipient, message):
        """
        Send text message via WhatsApp
        POST /api/send-message
        
        Args:
            session: WASenderSession instance
            recipient: Phone number (without + or country code)
            message: Message text
        
        Returns:
            WASenderMessage instance or None
        """
        # Check rate limits
        can_send, error_msg = session.can_send_message()
        if not can_send:
            logger.warning(f"Rate limit exceeded: {error_msg}")
            return None
        
        # Get session-specific API key
        session_api_key = self._decrypt_token(session.api_token)

        # Format and validate recipient
        recipient = self._format_phone_number(recipient)
        if not self._is_valid_e164(recipient):
            return WASenderMessage.objects.create(
                session=session,
                user=session.user,
                recipient=recipient,
                message_type='text',
                content=message,
                status='failed',
                error_message='Invalid phone number format'
            )

        # Soft preflight WhatsApp existence check
        try:
            exists_check = self.check_whatsapp(session, recipient.lstrip('+'))
            ok_flag = bool(exists_check.get('ok', False))
            exists_val = exists_check.get('exists', None)
            # Only block when the check succeeds and explicitly reports exists=False
            if ok_flag and isinstance(exists_val, bool) and exists_val is False:
                return WASenderMessage.objects.create(
                    session=session,
                    user=session.user,
                    recipient=recipient,
                    message_type='text',
                    content=message,
                    status='failed',
                    error_message='Number not registered on WhatsApp'
                )
            # If check fails or is inconclusive, proceed to attempt sending
        except Exception as _check_err:
            logger.warning(f"Preflight WhatsApp check unavailable, proceeding with send: {_check_err}")

        # Payload format expected by WASender
        payload = {
            "to": recipient,
            "type": "text",
            "text": message
        }
        
        try:
            response = requests.post(
                f"{self.BASE_URL}/send-message",
                headers=self._get_headers(session_api_key),
                json=payload,
                timeout=30
            )
            
            # Handle WASender rate limit (HTTP 429) by waiting and retrying once
            if response.status_code == 429:
                import time, json as _json
                try:
                    rate_data = response.json()
                except Exception:
                    try:
                        rate_data = _json.loads(response.text)
                    except Exception:
                        rate_data = {}
                retry_after = int(rate_data.get('retry_after', 5))
                logger.warning(f"Rate limited: waiting {retry_after}s before retrying text send")
                time.sleep(retry_after)
                response = requests.post(
                    f"{self.BASE_URL}/send-message",
                    headers=self._get_headers(session_api_key),
                    json=payload,
                    timeout=30
                )
            # Handle upstream server errors (HTTP 5xx) by retrying once after a short delay
            if response.status_code in (500, 502, 503, 504):
                import time
                logger.warning(f"Upstream 5xx ({response.status_code}) on text send; retrying once after 3s")
                time.sleep(3)
                response = requests.post(
                    f"{self.BASE_URL}/send-message",
                    headers=self._get_headers(session_api_key),
                    json=payload,
                    timeout=30
                )
            
            if response.status_code in [200, 201]:
                # Apply robust success detection similar to whatsappapi service
                data = {}
                try:
                    data = response.json()
                except Exception:
                    data = {}
                msg_data = data.get('data', data or {})

                raw_success = data.get('success')
                status_text = str(data.get('status', '')).lower()
                message_text = str(data.get('message', '')).lower()
                error_hints = ['not registered', 'invalid', 'fail', 'error', 'unavailable', 'bad request']

                if raw_success is not None:
                    success = bool(raw_success)
                elif status_text in ('success', 'ok', 'sent'):
                    success = True
                elif any(h in message_text for h in error_hints):
                    success = False
                else:
                    success = False

                if success:
                    msg = WASenderMessage.objects.create(
                        session=session,
                        user=session.user,
                        message_id=msg_data.get('id', str(msg_data.get('key', {}).get('id', ''))),
                        recipient=recipient,
                        message_type='text',
                        content=message,
                        status='sent',
                        sent_at=timezone.now()
                    )
                    session.increment_message_count()
                    logger.info(f"Message sent: {msg.message_id} to {recipient}")
                    return msg
                else:
                    error_msg = data.get('message') or response.text
                    # Sanitize HTML error pages (e.g., Cloudflare 5xx) to avoid dumping raw HTML
                    try:
                        content_type = response.headers.get('Content-Type', '')
                    except Exception:
                        content_type = ''
                    if ('text/html' in content_type) or ('<!DOCTYPE html' in str(error_msg)):
                        import re
                        ray_match = re.search(r'Cloudflare Ray ID:\s*([A-Za-z0-9]+)', str(error_msg))
                        ray_info = f" (Ray ID {ray_match.group(1)})" if ray_match else ''
                        error_msg = f"WASender API {response.status_code} HTML error page{ray_info}. Please retry later."
                    logger.error(f"Send-message API returned success=false: {error_msg}")
                    msg = WASenderMessage.objects.create(
                        session=session,
                        user=session.user,
                        recipient=recipient,
                        message_type='text',
                        content=message,
                        status='failed',
                        error_message=error_msg
                    )
                    return msg
            else:
            logger.error(f"Failed to send message: {response.status_code} - {_brief_response_text(response)}")
                
                # Create failed message record
                # Prefer JSON 'message' field when available, else sanitize HTML
                try:
                    data = response.json()
                except Exception:
                    data = {}
                try:
                    content_type = response.headers.get('Content-Type', '')
                except Exception:
                    content_type = ''
                error_text = data.get('message') or response.text
                if ('text/html' in content_type) or ('<!DOCTYPE html' in str(error_text)):
                    import re
                    ray_match = re.search(r'Cloudflare Ray ID:\s*([A-Za-z0-9]+)', str(error_text))
                    ray_info = f" (Ray ID {ray_match.group(1)})" if ray_match else ''
                    error_text = f"WASender API {response.status_code} HTML error page{ray_info}. Please retry later."
                msg = WASenderMessage.objects.create(
                    session=session,
                    user=session.user,
                    recipient=recipient,
                    message_type='text',
                    content=message,
                    status='failed',
                    error_message=error_text
                )
                return msg
                
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            
            # Create failed message record
            msg = WASenderMessage.objects.create(
                session=session,
                user=session.user,
                recipient=recipient,
                message_type='text',
                content=message,
                status='failed',
                error_message=str(e)
            )
            return msg
    
    def send_media_message(self, session, recipient, media_url, message_type='image', caption=''):
        """
        Send media message (image, video, document, audio)
        POST /api/send-message
        
        Args:
            session: WASenderSession instance
            recipient: Phone number (with country code)
            media_url: Public URL of media file
            message_type: 'image', 'video', 'document', 'audio'
            caption: Optional caption
        
        Returns:
            WASenderMessage instance or None
        """
        # Check rate limits
        can_send, error_msg = session.can_send_message()
        if not can_send:
            logger.warning(f"Rate limit exceeded: {error_msg}")
            return None
        
        session_api_key = self._decrypt_token(session.api_token)

        # Format and validate recipient
        recipient = self._format_phone_number(recipient)
        if not self._is_valid_e164(recipient):
            return WASenderMessage.objects.create(
                session=session,
                user=session.user,
                recipient=recipient,
                message_type=message_type,
                content=media_url,
                caption=caption,
                status='failed',
                error_message='Invalid phone number format'
            )

        # Soft preflight WhatsApp existence check
        try:
            exists_check = self.check_whatsapp(session, recipient.lstrip('+'))
            ok_flag = bool(exists_check.get('ok', False))
            exists_val = exists_check.get('exists', None)
            # Only block when the check succeeds and explicitly reports exists=False
            if ok_flag and isinstance(exists_val, bool) and exists_val is False:
                return WASenderMessage.objects.create(
                    session=session,
                    user=session.user,
                    recipient=recipient,
                    message_type=message_type,
                    content=media_url,
                    caption=caption,
                    status='failed',
                    error_message='Number not registered on WhatsApp'
                )
            # If check fails or is inconclusive, proceed to attempt sending
        except Exception as _check_err:
            logger.warning(f"Preflight WhatsApp check unavailable, proceeding with send: {_check_err}")
        
        # Use WASender url param names: imageUrl, videoUrl, documentUrl, audioUrl
        url_param_map = {
            'image': 'imageUrl',
            'video': 'videoUrl',
            'document': 'documentUrl',
            'audio': 'audioUrl'
        }
        url_param = url_param_map.get(message_type, 'imageUrl')
        payload = {
            "to": recipient,
            url_param: media_url
        }
        if caption:
            payload['text'] = caption
        if message_type == 'document':
            # include filename and mimetype for PDFs
            from urllib.parse import urlparse
            import os, mimetypes
            filename = os.path.basename(urlparse(media_url).path) or 'document.pdf'
            payload['fileName'] = filename
            mime, _ = mimetypes.guess_type(filename)
            if not mime and filename.lower().endswith('.pdf'):
                mime = 'application/pdf'
            if mime:
                payload['mimeType'] = mime
        
        try:
            response = requests.post(
                f"{self.BASE_URL}/send-message",
                headers=self._get_headers(session_api_key),
                json=payload,
                timeout=30
            )
            
            # Handle WASender rate limit (HTTP 429) by waiting and retrying once
            if response.status_code == 429:
                import time, json as _json
                try:
                    rate_data = response.json()
                except Exception:
                    try:
                        rate_data = _json.loads(response.text)
                    except Exception:
                        rate_data = {}
                retry_after = int(rate_data.get('retry_after', 5))
                logger.warning(f"Rate limited: waiting {retry_after}s before retrying media send")
                time.sleep(retry_after)
                response = requests.post(
                    f"{self.BASE_URL}/send-message",
                    headers=self._get_headers(session_api_key),
                    json=payload,
                    timeout=30
                )
            # Handle upstream server errors (HTTP 5xx) by retrying once after a short delay
            if response.status_code in (500, 502, 503, 504):
                import time
                logger.warning(f"Upstream 5xx ({response.status_code}) on media send; retrying once after 3s")
                time.sleep(3)
                response = requests.post(
                    f"{self.BASE_URL}/send-message",
                    headers=self._get_headers(session_api_key),
                    json=payload,
                    timeout=30
                )

            if response.status_code in [200, 201]:
                # Apply robust success detection similar to whatsappapi service
                data = {}
                try:
                    data = response.json()
                except Exception:
                    data = {}
                msg_data = data.get('data', data or {})
                raw_success = data.get('success')
                status_text = str(data.get('status', '')).lower()
                message_text = str(data.get('message', '')).lower()
                error_hints = ['not registered', 'invalid', 'fail', 'error', 'unavailable', 'bad request']

                if raw_success is not None:
                    success = bool(raw_success)
                elif status_text in ('success', 'ok', 'sent'):
                    success = True
                elif any(h in message_text for h in error_hints):
                    success = False
                else:
                    success = False

                if success:
                    msg = WASenderMessage.objects.create(
                        session=session,
                        user=session.user,
                        message_id=msg_data.get('id', str(msg_data.get('key', {}).get('id', ''))),
                        recipient=recipient,
                        message_type=message_type,
                        content=media_url,
                        caption=caption,
                        status='sent',
                        sent_at=timezone.now()
                    )
                    session.increment_message_count()
                    logger.info(f"Media message sent: {msg.message_id}")
                    return msg
                else:
                    error_msg = data.get('message') or response.text
                    # Sanitize HTML error pages (e.g., Cloudflare 5xx) to avoid dumping raw HTML
                    try:
                        content_type = response.headers.get('Content-Type', '')
                    except Exception:
                        content_type = ''
                    if ('text/html' in content_type) or ('<!DOCTYPE html' in str(error_msg)):
                        import re
                        ray_match = re.search(r'Cloudflare Ray ID:\s*([A-Za-z0-9]+)', str(error_msg))
                        ray_info = f" (Ray ID {ray_match.group(1)})" if ray_match else ''
                        error_msg = f"WASender API {response.status_code} HTML error page{ray_info}. Please retry later."
                    logger.error(f"Media send returned success=false: {error_msg}")
                    msg = WASenderMessage.objects.create(
                        session=session,
                        user=session.user,
                        recipient=recipient,
                        message_type=message_type,
                        content=media_url,
                        caption=caption,
                        status='failed',
                        error_message=error_msg
                    )
                    return msg
            else:
            logger.error(f"Failed to send media: {response.status_code} - {_brief_response_text(response)}")
                # Prefer JSON 'message' field when available, else sanitize HTML
                try:
                    data = response.json()
                except Exception:
                    data = {}
                try:
                    content_type = response.headers.get('Content-Type', '')
                except Exception:
                    content_type = ''
                error_text = data.get('message') or response.text
                if ('text/html' in content_type) or ('<!DOCTYPE html' in str(error_text)):
                    import re
                    ray_match = re.search(r'Cloudflare Ray ID:\s*([A-Za-z0-9]+)', str(error_text))
                    ray_info = f" (Ray ID {ray_match.group(1)})" if ray_match else ''
                    error_text = f"WASender API {response.status_code} HTML error page{ray_info}. Please retry later."
                msg = WASenderMessage.objects.create(
                    session=session,
                    user=session.user,
                    recipient=recipient,
                    message_type=message_type,
                    content=media_url,
                    caption=caption,
                    status='failed',
                    error_message=error_text
                )
                return msg
            
        except Exception as e:
            logger.error(f"Error sending media message: {e}")
            msg = WASenderMessage.objects.create(
                session=session,
                user=session.user,
                recipient=recipient,
                message_type=message_type,
                content=media_url,
                caption=caption,
                status='failed',
                error_message=str(e)
            )
            return msg
    
    # ==================== Webhook Processing ====================
    
    def process_webhook(self, payload):
        """
        Process incoming webhook from WASender
        
        Webhook Events:
        - messages.upsert: New incoming messages
        - connection.update: Session connection status changes
        
        Args:
            payload: Webhook JSON payload
        
        Returns:
            bool: True if processed successfully
        """
        try:
            # Check if it's a message event
            if 'data' in payload and 'messages' in payload['data']:
                return self._process_incoming_message(payload)
            
            # Check for connection update
            event_type = payload.get('event', '')
            if event_type == 'connection.update':
                return self._process_connection_update(payload)
            else:
                logger.warning(f"Unknown webhook event: {event_type}")
                return False
                
        except Exception as e:
            logger.error(f"Error processing webhook: {e}")
            return False
    
    def _process_incoming_message(self, payload):
        """
        Process incoming message from webhook
        Payload structure from WASender docs:
        {
            "data": {
                "messages": [
                    {
                        "key": {
                            "remoteJid": "1234567890@s.whatsapp.net",
                            "fromMe": false,
                            "id": "BAE5A93B52084A3B"
                        },
                        "message": {
                            "conversation": "Hello!"
                            // or "extendedTextMessage": {"text": "..."}
                            // or "imageMessage": {...}, etc.
                        },
                        "pushName": "John Doe",
                        "messageTimestamp": 1678886400
                    }
                ]
            }
        }
        """
        try:
            messages = payload.get('data', {}).get('messages', [])
            if not messages:
                return False
            
            for msg_data in messages:
                key = msg_data.get('key', {})
                message_obj = msg_data.get('message', {})
                
                # Extract message info
                message_id = key.get('id', '')
                remote_jid = key.get('remoteJid', '')
                from_me = key.get('fromMe', False)
                push_name = msg_data.get('pushName', 'Unknown')
                timestamp = msg_data.get('messageTimestamp', 0)
                
                # Extract phone number (remove @s.whatsapp.net)
                phone_number = remote_jid.replace('@s.whatsapp.net', '')
                
                # Skip messages sent by us
                if from_me:
                    continue
                
                # Extract message content
                message_text = None
                media_type = None
                media_url = None
                
                # Check for text
                if 'conversation' in message_obj:
                    message_text = message_obj['conversation']
                elif 'extendedTextMessage' in message_obj:
                    message_text = message_obj['extendedTextMessage'].get('text', '')
                
                # Check for media
                media_types = ['imageMessage', 'videoMessage', 'audioMessage', 'documentMessage', 'stickerMessage']
                for mtype in media_types:
                    if mtype in message_obj:
                        media_type = mtype.replace('Message', '')
                        media_info = message_obj[mtype]
                        media_url = media_info.get('url', '')
                        # Caption might exist
                        if not message_text and 'caption' in media_info:
                            message_text = media_info['caption']
                        break
                
                # Log received message
                logger.info(f"Received message from {phone_number}: {message_text or media_type}")
                
                # Find the session by phone number or webhook data
                # WASender should include session info in webhook
                session_id = payload.get('session_id') or payload.get('data', {}).get('session_id')
                
                session = None
                if session_id:
                    try:
                        session = WASenderSession.objects.get(session_id=session_id)
                    except WASenderSession.DoesNotExist:
                        logger.warning(f"Session not found: {session_id}")
                else:
                    # Try to find session by connected phone number
                    # This is fallback if session_id not in webhook
                    logger.warning("No session_id in webhook payload, searching by phone")
                
                if session:
                    # Store incoming message in database
                    try:
                        incoming_msg = WASenderIncomingMessage.objects.create(
                            session=session,
                            user=session.user,
                            message_id=message_id,
                            sender=phone_number,
                            sender_name=push_name,
                            message_type=media_type or 'text',
                            content=message_text or '',
                            media_url=media_url or '',
                            remote_jid=remote_jid,
                            timestamp=timestamp,
                            raw_data=msg_data
                        )
                        logger.info(f"Saved incoming message ID: {incoming_msg.id}")
                    except Exception as e:
                        logger.error(f"Error saving incoming message: {e}")
                else:
                    logger.warning("No session found for incoming message, skipping save")
                
            return True
                
        except Exception as e:
            logger.error(f"Error processing incoming message: {e}")
            return False
    
    def _process_connection_update(self, payload):
        """Process session connection status update"""
        try:
            session_id = payload.get('session_id', '')
            status = payload.get('status', '')
            
            try:
                session = WASenderSession.objects.get(session_id=session_id)
                session.status = status
                
                if status == 'connected':
                    session.connected_at = timezone.now()
                elif status == 'disconnected':
                    session.disconnected_at = timezone.now()
                
                session.save()
                logger.info(f"Session {session_id} status updated to {status}")
                return True
            except WASenderSession.DoesNotExist:
                logger.warning(f"Session not found: {session_id}")
                return False
                
        except Exception as e:
            logger.error(f"Error processing connection update: {e}")
            return False
