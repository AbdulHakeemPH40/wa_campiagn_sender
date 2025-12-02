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
from userpanel.models import WASenderSession, WASenderMessage, WASenderIncomingMessage

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
    
    # Base URL for WASender API. Allow override via Django settings.
    # Normalize by trimming trailing slashes to avoid double-slash routes.
    BASE_URL = getattr(settings, 'WASENDER_API_BASE_URL', 'https://wasenderapi.com/api').rstrip('/')
    
    def __init__(self):
        # Personal Access Token (from settings page) - used for session management
        self.personal_access_token = getattr(settings, 'WASENDER_PERSONAL_ACCESS_TOKEN', '')
        self.encryption_key = getattr(settings, 'ENCRYPTION_KEY', Fernet.generate_key())
        
        # Debug: Log token status
        if self.personal_access_token:
            logger.info(f"WASender API token loaded: {self.personal_access_token[:20]}...")
        else:
            logger.error("WASender API token NOT FOUND in settings!")
        # Log base URL in use
        logger.info(f"WASender BASE_URL: {self.BASE_URL}")
        # Runtime flag: whether upstream supports check-whatsapp endpoint
        # None = unknown, True = supported, False = unsupported
        self.check_whatsapp_supported = None
    
    def _get_headers(self, token=None):
        """Get API request headers with authentication"""
        return {
            "Authorization": f"Bearer {token or self.personal_access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            # Provide an explicit User-Agent to avoid generic clients being blocked by WAF/CDN
            "User-Agent": "WA-Campaign-Sender/1.0 (+https://wasenderapi.com)",
            # Help CDNs/WAFs treat these as API requests
            "X-Requested-With": "XMLHttpRequest",
            # Some gateways prefer a referer; allow override via settings
            "Referer": getattr(settings, 'WASENDER_REFERER', 'https://wasenderapi.com')
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
            # Avoid mistakenly sending Fernet ciphertext as a Bearer token.
            # If the token looks like Fernet ('gAAAAA' prefix), return empty string
            # so header generation falls back to the personal access token.
            try:
                looks_like_fernet = str(encrypted_token).startswith('gAAAAA')
            except Exception:
                looks_like_fernet = False
            logger.warning(f"Token decryption failed; looks_like_fernet={looks_like_fernet}. Error: {str(e)[:50]}")
            return '' if looks_like_fernet else encrypted_token

    def _send_with_retry(self, endpoint, headers, payload, max_retries=3, timeout=30):
        """
        Send HTTP POST request with exponential backoff retry logic.
        Handles timeouts, connection errors, 429 (rate limit), and 5xx errors.
        
        Args:
            endpoint: URL to POST to
            headers: HTTP headers
            payload: JSON payload
            max_retries: Maximum number of retry attempts (default: 3)
            timeout: Request timeout in seconds (default: 30)
            
        Returns:
            requests.Response object or None if all retries exhausted
        """
        import time
        
        for attempt in range(max_retries):
            try:
                response = requests.post(
                    endpoint,
                    headers=headers,
                    json=payload,
                    timeout=timeout
                )
                
                # Handle rate limiting (429) - respect retry_after
                if response.status_code == 429:
                    try:
                        rate_data = response.json()
                    except Exception:
                        rate_data = {}
                    retry_after = int(rate_data.get('retry_after', 2 ** attempt))
                    
                    if attempt == max_retries - 1:
                        logger.error(f"Rate limited after {max_retries} attempts. Final wait: {retry_after}s")
                        return response
                    
                    logger.warning(f"Rate limited (429). Retry {attempt + 1}/{max_retries} after {retry_after}s")
                    time.sleep(retry_after)
                    continue
                
                # Handle server errors (5xx) - exponential backoff
                if response.status_code >= 500:
                    if attempt == max_retries - 1:
                        logger.error(f"Server error ({response.status_code}) after {max_retries} attempts")
                        return response
                    
                    wait_time = 2 ** attempt  # 1, 2, 4 seconds
                    logger.warning(f"Server error ({response.status_code}). Retry {attempt + 1}/{max_retries} after {wait_time}s")
                    time.sleep(wait_time)
                    continue
                
                # Success or client error - return immediately
                return response
                
            except (requests.Timeout, requests.ConnectionError) as e:
                if attempt == max_retries - 1:
                    logger.error(f"Connection failed after {max_retries} attempts: {e}")
                    return None
                
                wait_time = 2 ** attempt  # 1, 2, 4 seconds
                logger.warning(f"Connection error (attempt {attempt + 1}/{max_retries}): {e}. Retry after {wait_time}s")
                time.sleep(wait_time)
                continue
            
            except Exception as e:
                logger.error(f"Unexpected error on attempt {attempt + 1}: {e}")
                if attempt == max_retries - 1:
                    return None
                time.sleep(2 ** attempt)
                continue
        
        return None
    
    def _is_api_available(self) -> bool:
        """Lightweight check to detect upstream outage (e.g., Cloudflare 5xx).

        Returns False when the base API appears to be down so callers can fail fast
        and avoid collapsing send logic with repeated 5xx HTML pages.
        """
        try:
            # HEAD first to avoid downloading HTML; treat 405/404 as available
            resp = requests.head(self.BASE_URL, headers=self._get_headers(), timeout=8, allow_redirects=True)
            if resp.status_code >= 500:
                return False
            if resp.status_code in (200, 301, 302, 304, 204, 405, 404):
                return True
            # As a fallback, a quick GET to confirm availability
            resp2 = requests.get(self.BASE_URL, headers=self._get_headers(), timeout=8, allow_redirects=True)
            return not (resp2.status_code >= 500)
        except Exception:
            return False
    
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
                logger.error(f"Failed to list sessions: {response.status_code} - {response.text}")
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
        if webhook_url and ('localhost' in webhook_url or '127.0.0.1' in webhook_url):
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
            elif response.status_code == 404:
                # Session doesn't exist on API - mark as disconnected locally
                logger.warning(f"Session not found on API (404): {session.session_id} - marking as disconnected locally")
                session.status = 'disconnected'
                session.disconnected_at = timezone.now()
                session.save()
                return True
            elif response.status_code in [502, 503, 504]:
                # Server error - API temporarily unavailable
                logger.error(f"WASender API temporarily unavailable ({response.status_code}): {_brief_response_text(response)}")
                return False
            else:
                logger.error(f"Failed to disconnect: {response.status_code} - {_brief_response_text(response)}")
                return False
                
        except requests.exceptions.Timeout:
            logger.error(f"Timeout disconnecting session {session.session_id} - API not responding")
            return False
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Connection error disconnecting session {session.session_id}: {e}")
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
    
    def _format_phone_number(self, phone):
        """
        Format phone number to E.164 format for WASender API
        Ensures phone number has + prefix
        
        Args:
            phone: Phone number string
        
        Returns:
            str: E.164 formatted phone (+1234567890)
        """
        if not phone:
            return ''
        
        # Remove all spaces, dashes, and other non-digit characters except +
        phone = ''.join(c for c in str(phone) if c.isdigit() or c == '+')
        
        # Ensure + prefix
        if not phone.startswith('+'):
            phone = '+' + phone
        
        return phone

    def _is_valid_e164(self, phone: str) -> bool:
        """
        International Standard E.164 phone number validation.
        Works for ALL countries without hardcoding specific country rules.
        
        E.164 is the international standard for phone numbers format:
        '+' followed by country code and national number (7-15 digits total).
        
        Validation rules (country-independent):
        1. Must start with '+'
        2. Must have 7-15 total digits (E.164 standard)
        3. Basic sanity checks only - WASender API validates actual
           WhatsApp account existence server-side
        
        Note: This validates the FORMAT only. WASender API validates actual
        WhatsApp account existence server-side.
        """
        try:
            s = str(phone or '')
        except Exception:
            return False
        
        import re
        
        # Must be E.164 format: + followed by 7-15 digits total
        if not re.match(r'^\+[0-9]+$', s):
            return False
        
        digits_only = s[1:]  # Remove +
        total_digits = len(digits_only)
        
        # E.164 standard: 7-15 digits total
        if not (7 <= total_digits <= 15):
            return False
        
        return True

    def _normalize_formatting(self, text: str) -> str:
        """
        Normalize user-entered formatting so WhatsApp renders monospace correctly.

        - Convert triple single quotes '''text''' to triple backticks ```text```.
        - Replace smart quotes with ASCII equivalents.
        - Handle accidental triple smart quotes.
        - Ensure fenced blocks use newline boundaries: ```\ntext\n``` for reliability.
        - Trim inner whitespace for inline markers: *bold*, _italic_, ~strike~.
        - Replace non-breaking and unusual spaces that break WhatsApp parser.
        - Remove zero-width joiners/spaces near markers.
        """
        try:
            s = str(text or '')
        except Exception:
            s = ''
        import re
        # Convert '''...''' to ```...```
        s = re.sub(r"'''([\s\S]*?)'''", r"```\1```", s)
        # Replace smart quotes that may appear from mobile keyboards
        s = s.replace('‘', "'").replace('’', "'").replace('´', "'")
        # Convert triple smart quotes to backticks as well
        s = re.sub(r"[’‘]{3}([\s\S]*?)[’‘]{3}", r"```\1```", s)
        # Ensure code fences have newline boundaries to avoid inline parsing issues
        def _fence_with_newlines(m):
            inner = m.group(1)
            # Trim to avoid trailing spaces inside fences
            inner_clean = inner.strip()
            return f"```\n{inner_clean}\n```"
        s = re.sub(r"```([\s\S]*?)```", _fence_with_newlines, s)

        # Normalize spaces that can break WhatsApp's inline formatting parser
        # Replace non-breaking spaces and figure spaces with normal space
        s = s.replace('\u00A0', ' ').replace('\u2007', ' ').replace('\u202F', ' ')
        # Remove zero-width characters that sometimes get copied from web/AI outputs
        s = s.replace('\u200B', '').replace('\u200C', '').replace('\u200D', '')

        # Trim inner whitespace at boundaries of inline markers so * text * -> *text*
        s = re.sub(r"\*([^*]+)\*", lambda m: '*' + (m.group(1).strip()) + '*', s)
        s = re.sub(r"_([^_]+)_", lambda m: '_' + (m.group(1).strip()) + '_', s)
        s = re.sub(r"~([^~]+)~", lambda m: '~' + (m.group(1).strip()) + '~', s)
        return s
    
    def validate_phone_batch(self, phone_list):
        """
        Validate a batch of phone numbers and return results.
        Useful for campaign uploads to show users which numbers are invalid.
        Filters out invalid numbers early to prevent silent failures.
        
        Args:
            phone_list: List of phone numbers (formatted or unformatted)
        
        Returns:
            dict: {
                "valid": [...valid phone numbers...],
                "invalid": [
                    {"phone": "...", "reason": "..."},
                    ...
                ],
                "summary": {
                    "total": int,
                    "valid_count": int,
                    "invalid_count": int,
                    "valid_percentage": int
                }
            }
        """
        valid_phones = []
        invalid_phones = []
        
        for phone in phone_list:
            try:
                if not phone:
                    invalid_phones.append({
                        "phone": str(phone),
                        "reason": "Empty phone number"
                    })
                    continue
                
                formatted = self._format_phone_number(phone)
                if not formatted:
                    invalid_phones.append({
                        "phone": str(phone),
                        "reason": "Failed to format phone number"
                    })
                elif not self._is_valid_e164(formatted):
                    invalid_phones.append({
                        "phone": str(phone),
                        "reason": f"Invalid E.164 format: expected +[country code][7-15 digits], got '{formatted}'"
                    })
                else:
                    valid_phones.append(formatted)
            except Exception as e:
                invalid_phones.append({
                    "phone": str(phone),
                    "reason": f"Validation error: {str(e)[:50]}"
                })
        
        return {
            "valid": valid_phones,
            "invalid": invalid_phones,
            "summary": {
                "total": len(phone_list),
                "valid_count": len(valid_phones),
                "invalid_count": len(invalid_phones),
                "valid_percentage": round(100 * len(valid_phones) / len(phone_list)) if phone_list else 0
            }
        }
    
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

        # Detect upstream outage early and fail fast with clear status
        if not self._is_api_available():
            error_text = "WASender API currently unavailable (upstream 5xx). Please retry later."
            if getattr(settings, 'WASENDER_QUEUE_ON_OUTAGE', False):
                return WASenderMessage.objects.create(
                    session=session,
                    user=session.user,
                    recipient=self._format_phone_number(recipient),
                    message_type='text',
                    content=message,
                    status='queued',
                    error_message=error_text
                )
            else:
                return WASenderMessage.objects.create(
                    session=session,
                    user=session.user,
                    recipient=self._format_phone_number(recipient),
                    message_type='text',
                    content=message,
                    status='failed',
                    error_message=error_text
                )
        
        # Format phone number to E.164
        recipient = self._format_phone_number(recipient)
        
        # Validate phone number format BEFORE sending to WASender
        if not self._is_valid_e164(recipient):
            error_msg = f"Invalid phone number format: {recipient}. Expected E.164 format with 7-15 digits."
            logger.warning(error_msg)
            return WASenderMessage.objects.create(
                session=session,
                user=session.user,
                recipient=recipient,
                message_type='text',
                content=message,
                status='failed',
                error_message=error_msg
            )
        
        # Payload format - simpler format that WASender expects
        payload = {
            "to": recipient,
            "type": "text",
            "text": message  # Direct string, not object
        }

        logger.info(f"Sending text to {recipient}: {repr(message)[:200]}")

        headers = self._get_headers(session_api_key)
        send_endpoints = [
            f"{self.BASE_URL}/send-message",
            f"{self.BASE_URL}/messages/send-message",
            f"{self.BASE_URL}/messages/send"
        ]

        response = None

        # Try each endpoint with retry logic
        for idx, ep in enumerate(send_endpoints):
            response = self._send_with_retry(ep, headers, payload, max_retries=3, timeout=30)
            
            if response is None:
                # Connection failed completely, try next endpoint
                if idx < len(send_endpoints) - 1:
                    logger.warning(f"Endpoint {ep} unavailable, trying fallback...")
                    continue
                else:
                    # All endpoints exhausted
                    logger.error(f"All send endpoints failed after retries")
                    return WASenderMessage.objects.create(
                        session=session,
                        user=session.user,
                        recipient=recipient,
                        message_type='text',
                        content=message,
                        status='failed',
                        error_message='Network connection failed after multiple retries. Please check your internet connection.'
                    )
            
            # If 200/201, break out and handle success
            if response.status_code in [200, 201]:
                break

            # If 404/405 on primary, try fallback endpoints; otherwise stop
            if response.status_code in [404, 405] and idx < len(send_endpoints) - 1:
                continue
            else:
                # Non-retryable or last endpoint; break and handle below
                break
        
        # Handle response after loop
        if response and response.status_code in [200, 201]:
            data = {}
            try:
                data = response.json()
            except Exception:
                data = {}
            msg_data = data.get('data', data or {})
            
            logger.info(f"WASender response for {recipient}: status_code={response.status_code}, full_data={data}")
            logger.info(f"DEBUG - msg_data keys: {msg_data.keys() if isinstance(msg_data, dict) else 'NOT A DICT'}, type: {type(msg_data)}")
            logger.info(f"DEBUG - Checking for message ID in: {msg_data}")
            
            # Check success based on response body indicators
            # Priority: explicit 'success' flag > 'status' field > error message hints > message ID
            success = False
            
            # 1. Check explicit 'success' field (most reliable)
            if 'success' in data:
                success_flag = bool(data.get('success'))
                # Check for message ID in multiple possible locations
                has_message_id = bool(
                    msg_data.get('id') or 
                    msg_data.get('msgId') or  # WASender uses msgId (camelCase)
                    msg_data.get('message_id') or
                    msg_data.get('key', {}).get('id') or
                    data.get('id') or  # Top level ID
                    data.get('msgId') or
                    data.get('message_id')
                )
                # Also check status field - must not be in error states
                status_text = str(msg_data.get('status', '')).lower()
                # Failed status indicators
                failed_statuses = ['failed', 'error', 'rejected', 'bounce']
                is_failed_status = status_text in failed_statuses
                
                if success_flag and has_message_id and not is_failed_status:
                    success = True
                elif success_flag and (not has_message_id or is_failed_status):
                    # success=true but no message ID or failed status - mark as failed
                    success = False
                    if is_failed_status:
                        logger.warning(f"WASender returned success=true but status is '{status_text}' - marking as failed")
                    else:
                        logger.warning(f"WASender returned success=true but no message ID - marking as failed")
                else:
                    # success=false - definitely failed
                    success = False
            # 2. Check 'status' field
            elif data.get('status'):
                status_text = str(data.get('status', '')).lower()
                success = status_text in ('success', 'ok', 'sent', 'queued')
            # 3. Check for error hints in message
            else:
                message_text = str(data.get('message', '')).lower()
                # Comprehensive error keywords that WASender might return
                error_hints = ['not registered', 'invalid', 'fail', 'error', 'unavailable', 'bad request', 'unknown', 'cannot', 'denied', 'does not exist', 'no account', 'unregistered', 'not found', 'rejected']
                has_error = any(h in message_text for h in error_hints)
                if has_error:
                    success = False
                else:
                    # 4. Fallback: check if message ID exists in response (multiple locations)
                    has_message_id = bool(
                        msg_data.get('id') or 
                        msg_data.get('msgId') or
                        msg_data.get('message_id') or
                        msg_data.get('key', {}).get('id') or
                        data.get('id') or
                        data.get('msgId') or
                        data.get('message_id')
                    )
                    success = has_message_id
                    if success:
                        logger.info(f"Success determined by message ID presence")
                    else:
                        # If no message ID and no success indicator, it's a FAILED message
                        # This handles cases where WASender returns 200/201 but number is invalid
                        success = False
                        logger.warning(f"WASender response missing success indicator - marking as failed. Response: {data}")
            
            if success:
                # Create message record as sent
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
                # Update session counters
                session.increment_message_count()
                logger.info(f"Message sent: {msg.message_id} to {recipient}")
                return msg
            else:
                error_msg = data.get('message') or response.text or 'No success indicator in WASender response (possible invalid number)'
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
            if response is None:
                logger.error(f"Failed to send message: No response (connection failed or all retries exhausted)")
                error_text = "Network connection failed. WASender API unreachable. Please check your internet connection and retry."
            else:
                logger.error(f"Failed to send message: {response.status_code} - {_brief_response_text(response) if response else 'No response'}")
                # Create failed message record
                # Prefer JSON 'message' field when available, else sanitize HTML
                try:
                    data = response.json() if response else {}
                except Exception:
                    data = {}
                try:
                    content_type = response.headers.get('Content-Type', '') if response else ''
                except Exception:
                    content_type = ''
                error_text = data.get('message') or (response.text if response else 'No response from API')
                if ('text/html' in content_type) or ('<!DOCTYPE html' in str(error_text)):
                    import re
                    ray_match = re.search(r'Cloudflare Ray ID:\s*([A-Za-z0-9]+)', str(error_text))
                    ray_info = f" (Ray ID {ray_match.group(1)})" if ray_match else ''
                    error_text = f"WASender API {response.status_code if response else 'unknown'} HTML error page{ray_info}. Please retry later."
            
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
    
    def upload_media_file(self, session, media_url, message_type='document', filename=None, public_id=None, file_bytes=None):
        """
        Upload media to Wasender first, then use returned public URL.
        Endpoint: POST /api/upload (per Wasender docs)

        Args:
            session: WASenderSession instance
            media_url: Public URL to fetch and upload
            message_type: 'document' | 'image' | 'video' | 'audio'
            filename: Optional filename hint

        Returns:
            str or None: The Wasender-hosted URL to use in send-message
        """
        try:
            session_api_key = self._decrypt_token(session.api_token)

            # Skip attempts when upstream is unavailable
            if not self._is_api_available():
                logger.error("WASender API unavailable; skipping pre-upload.")
                return None

            # 1) Try to download the bytes. If direct URL 401, use a signed Cloudinary private URL.
            clean_url = str(media_url).strip().strip('`"')
            # If bytes were provided (fresh upload), use them directly
            if file_bytes is None:
                try:
                    resp = requests.get(clean_url, timeout=60, allow_redirects=True)
                    if resp.status_code < 400:
                        file_bytes = resp.content
                    else:
                        logger.warning(f"Direct fetch failed ({resp.status_code}), attempting signed Cloudinary URL")
                except Exception as e:
                    logger.warning(f"Direct fetch error: {e}, attempting signed Cloudinary URL")

            if file_bytes is None:
                # Build signed download URL from Cloudinary
                try:
                    from urllib.parse import urlparse, unquote
                    import os
                    import cloudinary.utils
                    if public_id:
                        public_id_no_ext = public_id
                        ext = os.path.splitext(public_id)[1].replace('.', '') or 'pdf'
                    else:
                        parsed = urlparse(clean_url)
                        # Path looks like /<resource_type>/upload/v12345/<public_id>.<ext>
                        path = parsed.path
                        if '/upload/' in path:
                            after_upload = path.split('/upload/', 1)[1]
                        else:
                            after_upload = path
                        # Strip version prefix v12345/
                        if after_upload.startswith('v') and '/' in after_upload:
                            after_upload = after_upload.split('/', 1)[1]
                        public_id_with_ext = after_upload.lstrip('/')
                        # Unquote to avoid double-encoding (%20 becoming %2520)
                        public_id_with_ext = unquote(public_id_with_ext)
                        public_id_no_ext, ext = os.path.splitext(public_id_with_ext)
                    ext = (ext or '').replace('.', '') or 'pdf'
                    # First try authenticated signed URL (for assets with access_mode = authenticated)
                    signed_url, _opts = cloudinary.utils.cloudinary_url(
                        public_id_no_ext,
                        resource_type='raw',
                        type='authenticated',
                        sign_url=True,
                        format=ext
                    )
                    sresp = requests.get(signed_url, timeout=60, allow_redirects=True)
                    if sresp.status_code < 400:
                        file_bytes = sresp.content
                    else:
                        # Fallback to private download URL (for private assets)
                        signed_url = cloudinary.utils.private_download_url(
                            public_id_no_ext,
                            format=ext,
                            resource_type='raw',
                            attachment=False,
                            expires_at=None
                        )
                        sresp2 = requests.get(signed_url, timeout=60, allow_redirects=True)
                        if sresp2.status_code < 400:
                            file_bytes = sresp2.content
                        else:
                            logger.error(f"Signed Cloudinary download failed ({sresp.status_code}/{sresp2.status_code}) for {signed_url}")
                            return None
                except Exception as e:
                    logger.error(f"Error generating signed Cloudinary URL: {e}")
                    return None

            # 2) Base64 encode
            import base64
            base64_str = base64.b64encode(file_bytes).decode()

            # 3) Upload to Wasender using base64 field
            payload = {
                'type': message_type,
                'base64': base64_str
            }
            if filename:
                payload['fileName'] = filename

            # Some Wasender accounts expose the route under /messages/upload-media-file with PUT
            endpoint_primary = f"{self.BASE_URL}/messages/upload-media-file"
            endpoint_fallback = f"{self.BASE_URL}/upload-media-file"

            headers = self._get_headers(session_api_key)

            # Try PUT on /messages/upload-media-file first
            try:
                response = requests.put(
                    endpoint_primary,
                    headers=headers,
                    json=payload,
                    timeout=60
                )
            except Exception as e:
                logger.warning(f"PUT {endpoint_primary} error: {e}")
                response = requests.Response()
                response.status_code = 0

            # If 404/405, try POST on legacy /upload-media-file
            if response.status_code in [404, 405, 0]:
                try:
                    response = requests.post(
                        endpoint_fallback,
                        headers=headers,
                        json=payload,
                        timeout=60
                    )
                except Exception as e:
                    logger.warning(f"POST {endpoint_fallback} error: {e}")
                    response = requests.Response()
                    response.status_code = 0

            # As a final attempt, try PUT on legacy path
            if response.status_code in [404, 405, 0]:
                try:
                    response = requests.put(
                        endpoint_fallback,
                        headers=headers,
                        json=payload,
                        timeout=60
                    )
                except Exception as e:
                    logger.warning(f"PUT {endpoint_fallback} error: {e}")
                    response = requests.Response()
                    response.status_code = 0

            if response.status_code in [200, 201]:
                data = response.json()
                info = data.get('data', data)
                uploaded_url = (
                    info.get('url') or
                    info.get('mediaUrl') or
                    info.get('documentUrl') or
                    info.get('imageUrl') or
                    info.get('videoUrl') or
                    info.get('audioUrl')
                )
                if uploaded_url:
                    logger.info(f"Uploaded media to Wasender: {uploaded_url}")
                    return uploaded_url
                else:
                    logger.warning(f"Wasender upload successful but URL not found in response: {info}")
                    return None
            else:
                logger.error(f"Wasender upload failed: {response.status_code} - {_brief_response_text(response)}")
                return None
        except Exception as e:
            logger.error(f"Error uploading media to Wasender: {e}")
            return None

    def send_media_message(self, session, recipient, media_url, message_type='image', caption='', public_id=None):
        """
        Send media message (image, video, document, audio)
        POST /api/send-message
        
        Args:
            session: WASenderSession instance
            recipient: Phone number (with country code, e.g., +1234567890)
            media_url: Public URL of media file
            message_type: 'image', 'video', 'document', 'audio'
            caption: Optional caption/text message
        
        Returns:
            WASenderMessage instance or None
        """
        # Check rate limits
        can_send, error_msg = session.can_send_message()
        if not can_send:
            logger.warning(f"Rate limit exceeded: {error_msg}")
            return None
        
        session_api_key = self._decrypt_token(session.api_token)

        # Detect upstream outage early and fail fast with clear status
        if not self._is_api_available():
            error_text = "WASender API currently unavailable (upstream 5xx). Please retry later."
            if getattr(settings, 'WASENDER_QUEUE_ON_OUTAGE', False):
                return WASenderMessage.objects.create(
                    session=session,
                    user=session.user,
                    recipient=self._format_phone_number(recipient),
                    message_type=message_type,
                    content=media_url,
                    caption=caption,
                    status='queued',
                    error_message=error_text
                )
            else:
                return WASenderMessage.objects.create(
                    session=session,
                    user=session.user,
                    recipient=self._format_phone_number(recipient),
                    message_type=message_type,
                    content=media_url,
                    caption=caption,
                    status='failed',
                    error_message=error_text
                )
        
        # Format phone number to E.164
        recipient = self._format_phone_number(recipient)
        
        # Validate phone number format BEFORE sending to WASender
        if not self._is_valid_e164(recipient):
            error_msg = f"Invalid phone number format: {recipient}. Expected E.164 format with 7-15 digits."
            logger.warning(error_msg)
            return WASenderMessage.objects.create(
                session=session,
                user=session.user,
                recipient=recipient,
                message_type=message_type,
                content=media_url,
                caption=caption,
                status='failed',
                error_message=error_msg
            )
        
        # Sanitize URL to avoid accidental backticks/quotes from UI or logs
        def _sanitize_url(u: str) -> str:
            try:
                return str(u).strip().strip('`"')
            except Exception:
                return str(u)

        media_url = _sanitize_url(media_url)

        # WASender API format - use specific URL parameter names
        # imageUrl, videoUrl, documentUrl, audioUrl
        url_param_map = {
            'image': 'imageUrl',
            'video': 'videoUrl',
            'document': 'documentUrl',
            'audio': 'audioUrl'
        }
        
        url_param = url_param_map.get(message_type, 'imageUrl')
        
        # Normalize caption formatting before building payload
        caption = self._normalize_formatting(caption)

        # Build payload according to WASender API documentation
        # For media messages, WASender may require JID format: [phone]@s.whatsapp.net
        # (without + prefix, using @s.whatsapp.net suffix for user messages)
        recipient_for_api = recipient.lstrip('+')  # Remove + prefix if present
        recipient_jid = f"{recipient_for_api}@s.whatsapp.net" if not recipient_for_api.endswith('@s.whatsapp.net') else recipient_for_api
        
        payload = {
            "to": recipient_jid,  # JID format for media: [phone]@s.whatsapp.net
            url_param: media_url,
            "type": message_type
        }
        
        # Add caption/text if provided
        if caption:
            payload['text'] = caption
        
        # For document messages, some APIs require additional parameters
        if message_type == 'document' and media_url:
            # Extract filename for document messages (WASender expects fileName)
            from urllib.parse import urlparse
            from urllib.parse import unquote
            import os, mimetypes
            parsed_url = urlparse(media_url)
            filename = os.path.basename(parsed_url.path) or 'document.pdf'
            filename = unquote(filename)
            payload['fileName'] = filename
            # Include mimeType when known (helps WASender classify PDF/doc types)
            mime, _ = mimetypes.guess_type(filename)
            if not mime and filename.lower().endswith('.pdf'):
                mime = 'application/pdf'
            if mime:
                payload['mimeType'] = mime

            # Only pre-upload to Wasender if media_url is not publicly accessible
            try:
                head_resp = requests.head(media_url, timeout=10, allow_redirects=True)
                if head_resp.status_code >= 400:
                    uploaded_url = self.upload_media_file(session, media_url, 'document', filename, public_id)
                    if uploaded_url:
                        payload[url_param] = uploaded_url
                        media_url = uploaded_url
            except Exception:
                # If HEAD fails unexpectedly, proceed with original URL
                pass
        
        # Preflight: ensure URL is publicly accessible (avoid Wasender fetch 401/403)
        # Skip strict preflight for audio, as some CDNs block HEAD on audio resources
        if message_type != 'audio':
            try:
                head_resp = requests.head(media_url, timeout=10, allow_redirects=True)
                if head_resp.status_code >= 400:
                    # Attempt pre-upload to Wasender as a fallback for blocked URLs
                    from urllib.parse import urlparse
                    import os
                    fallback_filename = os.path.basename(urlparse(media_url).path) or None
                    uploaded_url = self.upload_media_file(
                        session,
                        media_url,
                        message_type,
                        fallback_filename,
                        public_id
                    )
                    if uploaded_url:
                        payload[url_param] = uploaded_url
                        media_url = uploaded_url
                    else:
                        logger.error(f"Media URL not publicly accessible ({head_resp.status_code}) and upload failed: {media_url}")
                        return None
            except Exception as e:
                # If HEAD fails unexpectedly, try uploading as a last resort
                try:
                    from urllib.parse import urlparse
                    import os
                    fallback_filename = os.path.basename(urlparse(media_url).path) or None
                    uploaded_url = self.upload_media_file(
                        session,
                        media_url,
                        message_type,
                        fallback_filename,
                        public_id
                    )
                    if uploaded_url:
                        payload[url_param] = uploaded_url
                        media_url = uploaded_url
                    else:
                        logger.error(f"Error checking media URL access and upload failed: {e}")
                        return None
                except Exception as ex:
                    logger.error(f"Error checking media URL access: {ex}")
                    return None

        logger.info(f"Sending {message_type} to {recipient}: {payload}")
        
        try:
            headers = self._get_headers(session_api_key)
            send_endpoints = [
                f"{self.BASE_URL}/send-message",
                f"{self.BASE_URL}/messages/send-message",
                f"{self.BASE_URL}/messages/send"
            ]

            response = None

            for idx, ep in enumerate(send_endpoints):
                try:
                    response = requests.post(
                        ep,
                        headers=headers,
                        json=payload,
                        timeout=30
                    )
                except Exception as e:
                    logger.warning(f"POST {ep} error: {e}")
                    # Construct a dummy response object with status_code 0
                    response = requests.Response()
                    response.status_code = 0

                # Handle WASender rate limit (HTTP 429) by waiting and retrying once on the same endpoint
                if response.status_code == 429:
                    import time, json as _json
                    try:
                        rate_data = response.json()
                    except Exception:
                        try:
                            rate_data = _json.loads(getattr(response, 'text', '') or '{}')
                        except Exception:
                            rate_data = {}
                    retry_after = int(rate_data.get('retry_after', 5))
                    logger.warning(f"Rate limited: waiting {retry_after}s before retrying media send")
                    time.sleep(retry_after)
                    try:
                        response = requests.post(
                            ep,
                            headers=headers,
                            json=payload,
                            timeout=30
                        )
                    except Exception as re:
                        logger.warning(f"Retry POST {ep} error after 429 wait: {re}")
                        response = requests.Response()
                        response.status_code = 0

                # Handle upstream server errors (HTTP 5xx) by retrying once on the same endpoint
                if response.status_code in (500, 502, 503, 504):
                    import time
                    logger.warning(f"Upstream 5xx ({response.status_code}) on media send; retrying once after 3s")
                    time.sleep(3)
                    try:
                        response = requests.post(
                            ep,
                            headers=headers,
                            json=payload,
                            timeout=30
                        )
                    except Exception as re2:
                        logger.warning(f"Retry POST {ep} error after 5xx wait: {re2}")
                        response = requests.Response()
                        response.status_code = 0

                # If 200/201, break out and handle success
                if response.status_code in [200, 201]:
                    break

                # If 404/405/0 on primary, try fallback endpoints; otherwise stop
                if response.status_code in [404, 405, 0] and idx < len(send_endpoints) - 1:
                    continue
                else:
                    # Non-retryable or last endpoint; break and handle below
                    break

            if response.status_code in [200, 201]:
                data = {}
                try:
                    data = response.json()
                except Exception:
                    data = {}
                msg_data = data.get('data', data or {})

                # Check success based on response body indicators
                # Priority: explicit 'success' flag > 'status' field > error message hints > message ID
                success = False
                
                # 1. Check explicit 'success' field (most reliable)
                if 'success' in data:
                    success_flag = bool(data.get('success'))
                    # Check for message ID in multiple possible locations
                    has_message_id = bool(
                        msg_data.get('id') or 
                        msg_data.get('msgId') or  # WASender uses msgId (camelCase)
                        msg_data.get('message_id') or
                        msg_data.get('key', {}).get('id') or
                        data.get('id') or  # Top level ID
                        data.get('msgId') or
                        data.get('message_id')  # Alternative field name
                    )
                    # Also check status field - must not be in error states
                    status_text = str(msg_data.get('status', '')).lower()
                    # Failed status indicators
                    failed_statuses = ['failed', 'error', 'rejected', 'bounce']
                    is_failed_status = status_text in failed_statuses
                    
                    if success_flag and has_message_id and not is_failed_status:
                        success = True
                    elif success_flag and (not has_message_id or is_failed_status):
                        # success=true but no message ID or failed status - mark as failed
                        success = False
                        if is_failed_status:
                            logger.warning(f"WASender returned success=true but status is '{status_text}' (media) - marking as failed")
                        else:
                            logger.warning(f"WASender returned success=true but no message ID (media) - marking as failed")
                    else:
                        # success=false - definitely failed
                        success = False
                # 2. Check 'status' field
                elif data.get('status'):
                    status_text = str(data.get('status', '')).lower()
                    success = status_text in ('success', 'ok', 'sent', 'queued')
                # 3. Check for error hints in message
                else:
                    message_text = str(data.get('message', '')).lower()
                    # Comprehensive error keywords that WASender might return
                    error_hints = ['not registered', 'invalid', 'fail', 'error', 'unavailable', 'bad request', 'unknown', 'cannot', 'denied', 'does not exist', 'no account', 'unregistered', 'not found', 'rejected']
                    has_error = any(h in message_text for h in error_hints)
                    if has_error:
                        success = False
                    else:
                        # 4. Fallback: check if message ID exists in response (multiple locations)
                        has_message_id = bool(
                            msg_data.get('id') or 
                            msg_data.get('msgId') or
                            msg_data.get('message_id') or
                            msg_data.get('key', {}).get('id') or
                            data.get('id') or
                            data.get('msgId') or
                            data.get('message_id')
                        )
                        success = has_message_id
                        if success:
                            logger.info(f"Success determined by message ID presence (media)")
                        else:
                            # If no message ID and no success indicator, it's a FAILED message
                            # This handles cases where WASender returns 200/201 but number is invalid
                            success = False
                            logger.warning(f"WASender response missing success indicator (media) - marking as failed. Response: {data}")

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
                    logger.info(f"Media message sent successfully: {msg.message_id}")
                    return msg
                else:
                    error_msg = data.get('message') or response.text or 'No success indicator in WASender response (possible invalid number)'
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
                if response is None:
                    logger.error(f"Failed to send media: No response (connection failed or all retries exhausted)")
                    error_text = "Network connection failed. WASender API unreachable. Please check your internet connection and retry."
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
    
    # ==================== Contact Management ====================
    
    def check_whatsapp(self, session, phone_number):
        """
        Check if a phone number is registered on WhatsApp
        GET /api/check-whatsapp?phone={phone}
        
        Args:
            session: WASenderSession instance
            phone_number: Phone number to check (with country code, no +)
        
        Returns:
            dict: {'exists': True/False, 'jid': '1234567890@s.whatsapp.net', 'ok': True/False, 'error': str}
        """
        try:
            session_api_key = self._decrypt_token(session.api_token)
            # Fail fast during an outage to avoid misleading HTML 5xx content
            if not self._is_api_available():
                return {
                    'ok': False,
                    'exists': None,
                    'error': 'WASender API currently unavailable (upstream 5xx). Please retry later.',
                    'status_code': 503,
                }
            # Try multiple endpoint variants to accommodate different deployments
            endpoints = [
                f"{self.BASE_URL}/check-whatsapp",
                f"{self.BASE_URL}/messages/check-whatsapp",
                f"{self.BASE_URL}/whatsapp/check",
            ]

            # Prefer no-plus format for this endpoint to reduce retries
            phone_variants = [str(phone_number or '').lstrip('+')]

            headers = self._get_headers(session_api_key)

            def _do_check(ep, ph):
                return requests.get(
                    ep,
                    params={'phone': ph},
                    headers=headers,
                    timeout=30
                )

            response = None
            last_response = None
            for ep in endpoints:
                for ph in phone_variants:
                    try:
                        resp = _do_check(ep, ph)
                    except Exception as e:
                        logger.warning(f"check-whatsapp request error at {ep} [{ph}]: {e}")
                        continue
                    # Skip obvious 404/405 and try next endpoint
                    if resp.status_code in (404, 405):
                        logger.info(f"check-whatsapp endpoint {ep} not found ({resp.status_code}); trying next")
                        last_response = resp
                        continue
                    # If upstream returns HTML 5xx, try next endpoint variant before retrying
                    try:
                        ct = resp.headers.get('Content-Type', '')
                    except Exception:
                        ct = ''
                    if resp.status_code in (500, 502, 503, 504) and 'text/html' in ct:
                        logger.warning(f"Endpoint {ep} returned HTML {resp.status_code}; trying fallback endpoint")
                        last_response = resp
                        continue
                    response = resp
                    break
                if response is not None:
                    break
            if response is None:
                response = last_response

            # Handle rate limit (HTTP 429): respect retry_after and retry once
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
                # Retry using the first endpoint and first phone variant to minimize noise
                response = _do_check(endpoints[0], phone_variants[0])

            # Handle upstream server errors (HTTP 5xx): retry once after short delay
            if response.status_code in (500, 502, 503, 504):
                import time
                logger.warning(f"Upstream 5xx ({response.status_code}) on check-whatsapp; retrying once after 3s")
                time.sleep(3)
                response = _do_check(endpoints[0], phone_variants[0])

            if response.status_code == 200:
                data = response.json()
                result = data.get('data', {})
                # Infer existence from explicit flag or presence of jid
                exists = result.get('exists')
                if exists is None:
                    exists = bool(result.get('jid'))
                result['exists'] = bool(exists)
                result['ok'] = True
                logger.info(f"WhatsApp check for {phone_number}: {result}")
                return result
            else:
                # If endpoint not found, mark unsupported to skip future checks
                if response.status_code in (404, 405):
                    self.check_whatsapp_supported = False
                logger.error(f"Failed to check WhatsApp: {response.status_code} - {_brief_response_text(response)}")
                return {'exists': False, 'ok': False, 'error': _brief_response_text(response), 'status_code': response.status_code}
                
        except Exception as e:
            logger.error(f"Error checking WhatsApp: {e}")
            return {'exists': False, 'ok': False, 'error': str(e)}
    
    def get_contacts(self, session):
        """
        Get contacts from connected WhatsApp
        GET /api/contacts
        
        Args:
            session: WASenderSession instance
        
        Returns:
            list: List of contact dicts
        """
        try:
            session_api_key = self._decrypt_token(session.api_token)
            
            response = requests.get(
                f"{self.BASE_URL}/contacts",
                headers=self._get_headers(session_api_key),
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                contacts = data.get('data', [])
                logger.info(f"Retrieved {len(contacts)} contacts from WhatsApp")
                return contacts
            else:
                logger.error(f"Failed to get contacts: {response.status_code} - {_brief_response_text(response)}")
                return []
                
        except Exception as e:
            logger.error(f"Error getting contacts: {e}")
            return []
    
    def get_profile_picture(self, session, phone_number):
        """
        Get profile picture URL for a WhatsApp contact
        GET /api/profile-picture?phone={phone}
        
        Args:
            session: WASenderSession instance
            phone_number: Phone number (with country code, no +)
        
        Returns:
            str: Profile picture URL or empty string
        """
        try:
            session_api_key = self._decrypt_token(session.api_token)
            
            response = requests.get(
                f"{self.BASE_URL}/profile-picture",
                params={'phone': phone_number},
                headers=self._get_headers(session_api_key),
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                pic_url = data.get('data', {}).get('url', '')
                return pic_url
            else:
                logger.error(f"Failed to get profile picture: {response.status_code}")
                return ''
                
        except Exception as e:
            logger.error(f"Error getting profile picture: {e}")
            return ''
