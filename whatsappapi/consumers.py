"""
WebSocket Consumers for Real-time Updates
Handles campaign progress, message delivery, and chat messages
"""

import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser

logger = logging.getLogger(__name__)


class UpdatesConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for real-time campaign updates.
    Sends live progress, message delivery status, and chat messages.
    
    Connection format: ws://localhost:8000/ws/updates/
    """
    
    async def connect(self):
        """Handle WebSocket connection."""
        self.user = self.scope['user']
        
        # Only authenticated users can connect
        if self.user.is_authenticated:
            self.user_group = f"updates_{self.user.id}"
            await self.channel_layer.group_add(self.user_group, self.channel_name)
            await self.accept()
            logger.info(f"WebSocket connected for user {self.user.email}")
        else:
            logger.warning("WebSocket connection attempt by anonymous user - rejected")
            await self.close()
    
    async def disconnect(self, close_code):
        """Handle WebSocket disconnection."""
        if self.user.is_authenticated:
            await self.channel_layer.group_discard(self.user_group, self.channel_name)
            logger.info(f"WebSocket disconnected for user {self.user.email} (code: {close_code})")
    
    async def receive(self, text_data):
        """
        Handle incoming WebSocket messages from client.
        Supports ping/pong for connection health checks.
        """
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            if message_type == 'ping':
                # Respond to ping requests (connection health check)
                await self.send(text_data=json.dumps({'type': 'pong', 'timestamp': str(__import__('django.utils.timezone', fromlist=['now']).now())}))
                logger.debug(f"Ping received from user {self.user.email}")
            
            elif message_type == 'subscribe':
                # Client can subscribe to specific campaign updates
                campaign_id = data.get('campaign_id')
                if campaign_id:
                    self.campaign_group = f"campaign_{campaign_id}"
                    await self.channel_layer.group_add(self.campaign_group, self.channel_name)
                    logger.info(f"User {self.user.email} subscribed to campaign {campaign_id}")
            
            else:
                logger.warning(f"Unknown message type received: {message_type}")
        
        except json.JSONDecodeError:
            logger.error("Invalid JSON received on WebSocket")
            await self.send(text_data=json.dumps({'error': 'Invalid JSON format'}))
        except Exception as e:
            logger.error(f"Error processing WebSocket message: {e}")
    
    # ==================== Event Handlers for Group Messages ====================
    
    async def campaign_update(self, event):
        """
        Send campaign progress updates to client.
        Called when campaign status changes.
        """
        try:
            await self.send(text_data=json.dumps({
                'type': 'campaign_update',
                'campaign_id': event.get('campaign_id'),
                'campaign_name': event.get('campaign_name'),
                'status': event.get('status'),  # running, paused, completed, failed
                'sent_count': event.get('sent_count', 0),
                'failed_count': event.get('failed_count', 0),
                'total_contacts': event.get('total_contacts', 0),
                'progress_percent': event.get('progress_percent', 0),
                'message': event.get('message', ''),
                'timestamp': event.get('timestamp')
            }))
            logger.debug(f"Campaign update sent to user {self.user.email}: {event.get('campaign_id')}")
        except Exception as e:
            logger.error(f"Error sending campaign update: {e}")
    
    async def message_delivery(self, event):
        """
        Send individual message delivery status updates to client.
        Called when a message is sent/failed.
        """
        try:
            await self.send(text_data=json.dumps({
                'type': 'message_delivery',
                'message_id': event.get('message_id'),
                'campaign_id': event.get('campaign_id'),
                'status': event.get('status'),  # sent, failed, delivered
                'recipient': event.get('recipient'),
                'error_message': event.get('error_message', ''),
                'timestamp': event.get('timestamp')
            }))
            logger.debug(f"Message delivery update sent for {event.get('message_id')}")
        except Exception as e:
            logger.error(f"Error sending message delivery update: {e}")
    
    async def chat_message(self, event):
        """
        Send chat messages to client (for real-time chat feature).
        Called when new messages are received.
        """
        try:
            await self.send(text_data=json.dumps({
                'type': 'chat_message',
                'message': event.get('message'),
                'sender': event.get('sender'),
                'sender_id': event.get('sender_id'),
                'room': event.get('room'),
                'timestamp': event.get('timestamp')
            }))
            logger.debug(f"Chat message sent to user {self.user.email}")
        except Exception as e:
            logger.error(f"Error sending chat message: {e}")
    
    async def notification(self, event):
        """
        Send general notifications to client.
        Called for important events (subscription expired, limit reached, etc.)
        """
        try:
            await self.send(text_data=json.dumps({
                'type': 'notification',
                'level': event.get('level', 'info'),  # info, warning, error, success
                'title': event.get('title'),
                'message': event.get('message'),
                'action_url': event.get('action_url'),
                'timestamp': event.get('timestamp')
            }))
            logger.debug(f"Notification sent to user {self.user.email}")
        except Exception as e:
            logger.error(f"Error sending notification: {e}")
    
    async def session_status(self, event):
        """
        Send WhatsApp session status updates to client.
        Called when session connects/disconnects.
        Enables real-time dashboard updates and QR code prompt on disconnect.
        """
        try:
            await self.send(text_data=json.dumps({
                'type': 'session_status',
                'session_id': event.get('session_id'),
                'session_name': event.get('session_name', ''),
                'status': event.get('status'),  # connected, disconnected, pending, need_scan, error
                'phone_number': event.get('phone_number'),
                'message': event.get('message', ''),
                'timestamp': event.get('timestamp'),
                'needs_reconnect': event.get('needs_reconnect', False)  # True if QR scan needed
            }))
            logger.info(f"📡 Session status update sent | Session: {event.get('session_id')} | Status: {event.get('status')}")
        except Exception as e:
            logger.error(f"Error sending session status update: {e}")
