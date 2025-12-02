"""
WASender Integration Views
Handles WhatsApp session management and campaign sending
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponseForbidden
from django.views.decorators.http import require_POST, require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.urls import reverse
from django.utils import timezone
from django.conf import settings
import json
import logging

from .models import WASenderSession, WASenderMessage, WASenderCampaign
from whatsappapi.wasender_service import WASenderService
from adminpanel.models import Subscription

logger = logging.getLogger(__name__)


# ==================== Session Management Views ====================

@login_required
def whatsapp_dashboard(request):
    """
    Main WA Sender dashboard
    Shows sessions, stats, and recent messages
    """
    # Get user's active session (connected or pending)
    active_session = WASenderSession.objects.filter(
        user=request.user,
        status__in=['connected', 'pending', 'disconnected']  # Include disconnected
    ).first()
    
    # If session exists, update its status from WASender API
    if active_session:
        service = WASenderService()
        try:
            service.get_session_status(active_session)  # This updates status in DB
        except Exception as e:
            logger.error(f"Error updating session status: {e}")
    
    # Get all user sessions
    all_sessions = WASenderSession.objects.filter(user=request.user).order_by('-created_at')[:10]
    
    # Get recent messages
    recent_messages = WASenderMessage.objects.filter(user=request.user).order_by('-created_at')[:20]
    
    # Get campaigns
    campaigns = WASenderCampaign.objects.filter(user=request.user).order_by('-created_at')[:10]
    
    # Calculate stats
    total_messages = WASenderMessage.objects.filter(user=request.user).count()
    sent_today = WASenderMessage.objects.filter(
        user=request.user,
        created_at__date=timezone.now().date()
    ).count()
    
    context = {
        'active_session': active_session,
        'all_sessions': all_sessions,
        'recent_messages': recent_messages,
        'campaigns': campaigns,
        'total_messages': total_messages,
        'sent_today': sent_today,
    }
    
    return render(request, 'userpanel/whatsapp_dashboard.html', context)


@login_required
def create_whatsapp_session(request):
    """
    Create new WhatsApp session - Get phone number from user
    """
    if request.method == 'POST':
        phone_number = request.POST.get('phone_number', '').strip()
        
        if not phone_number:
            messages.error(request, "Phone number is required")
            return redirect('userpanel:whatsapp_dashboard')
        
        # Check if user already has an active session
        existing_session = WASenderSession.objects.filter(
            user=request.user,
            status__in=['connected', 'pending', 'disconnected']
        ).first()
        
        if existing_session:
            messages.warning(request, "You already have an active session")
            return redirect('userpanel:connect_whatsapp', session_id=existing_session.id)
        
        # Create new session
        service = WASenderService()
        webhook_url = request.build_absolute_uri(
            reverse('userpanel:wasender_webhook', args=[request.user.id])
        )
        
        try:
            session = service.create_session(request.user, webhook_url, phone_number)
            if session:
                # Initiate connection to get QR code
                service.connect_session(session)
                messages.success(request, "Session created! Please scan QR code to connect")
                return redirect('userpanel:connect_whatsapp', session_id=session.id)
            else:
                # Session creation returned None (should not happen with new error handling)
                messages.error(request, "Failed to create session. Please try again or contact support.")
                return redirect('userpanel:whatsapp_dashboard')
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error creating session: {error_msg}")
            
            # Show user-friendly error messages
            if "Session limit reached" in error_msg or "upgrade your plan" in error_msg.lower():
                messages.error(
                    request, 
                    "You have reached your WhatsApp session limit on WASender. Please delete an existing session or upgrade your plan at https://wasenderapi.com/pricing"
                )
            elif "phone number has already been taken" in error_msg.lower():
                messages.error(
                    request, 
                    "This phone number is already registered with another session. Please delete the old session from WASender dashboard first."
                )
            else:
                messages.error(request, f"Failed to create session: {error_msg}")
            
            return redirect('userpanel:whatsapp_dashboard')
    
    # GET request - show phone input form
    return render(request, 'userpanel:whatsapp_dashboard.html')


@login_required
def connect_whatsapp(request, session_id):
    """
    Show QR code for WhatsApp connection
    """
    session = get_object_or_404(WASenderSession, id=session_id, user=request.user)
    
    service = WASenderService()
    
    # Always call connect first to ensure session is ready for QR
    if session.status in ['disconnected', 'logged_out']:
        logger.info(f"Session {session.session_id} is {session.status}, calling connect...")
        service.connect_session(session)
    
    # Get QR code if session is pending/need_scan
    qr_code = None
    if session.status in ['pending', 'need_scan']:
        try:
            qr_code = service.get_qr_code(session)
        except Exception as e:
            logger.error(f"Error getting QR code: {e}")
            messages.error(request, "Failed to get QR code. Please try again")
    
    context = {
        'session': session,
        'qr_code': qr_code,
    }
    
    return render(request, 'userpanel/whatsapp_connect.html', context)


@login_required
@require_POST
def check_session_status(request, session_id):
    """
    AJAX endpoint to check session connection status
    """
    session = get_object_or_404(WASenderSession, id=session_id, user=request.user)
    
    service = WASenderService()
    try:
        status_data = service.get_session_status(session)
        return JsonResponse({
            'status': session.status,
            'phone_number': session.phone_number or '',
            'connected': session.status == 'connected',
            'data': status_data
        })
    except Exception as e:
        logger.error(f"Error checking status: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_POST
def disconnect_session(request, session_id):
    """
    Disconnect WhatsApp session
    """
    session = get_object_or_404(WASenderSession, id=session_id, user=request.user)
    
    service = WASenderService()
    try:
        if service.disconnect_session(session):
            messages.success(request, "Session disconnected successfully")
        else:
            messages.error(request, "Failed to disconnect session")
    except Exception as e:
        logger.error(f"Error disconnecting session: {e}")
        messages.error(request, f"Error: {str(e)}")
    
    return redirect('userpanel:whatsapp_dashboard')


@login_required
@require_POST
def delete_session(request, session_id):
    """
    Delete WhatsApp session
    """
    session = get_object_or_404(WASenderSession, id=session_id, user=request.user)
    session_id_text = session.session_id
    
    service = WASenderService()
    try:
        # Try to delete from WASender API
        # Returns True even if session doesn't exist (404)
        api_deleted = service.delete_session(session)
        
        # Always delete from local database
        session.delete()
        
        if api_deleted:
            messages.success(request, "Session deleted successfully")
        else:
            # API deletion failed but local deletion succeeded
            messages.warning(
                request,
                f"Session deleted from your account, but removal from WASender failed. "
                f"You may need to manually delete session {session_id_text} from WASender dashboard."
            )
    except Exception as e:
        logger.error(f"Error deleting session: {e}")
        messages.error(request, f"Error: {str(e)}")
    
    return redirect('userpanel:whatsapp_dashboard')


# ==================== Message Sending Views ====================

@login_required
def send_campaign_view(request):
    """
    Send WhatsApp campaign view
    """
    # Get user's active session
    session = WASenderSession.objects.filter(
        user=request.user,
        status='connected'
    ).first()
    
    if not session:
        messages.error(request, "Please connect WhatsApp first")
        return redirect('userpanel:create_whatsapp_session')
    
    # Check for phone number mismatch
    if session.phone_number and session.connected_phone_number:
        if session.phone_number != session.connected_phone_number:
            messages.error(
                request, 
                f"Phone number mismatch! You registered with {session.phone_number} but scanned with {session.connected_phone_number}. "
                f"Please delete this session and create a new one with {session.connected_phone_number}."
            )
            return redirect('userpanel:whatsapp_dashboard')
    
    if request.method == 'POST':
        message = request.POST.get('message', '').strip()
        recipients = request.POST.get('recipients', '').strip()
        
        if not message or not recipients:
            messages.error(request, "Message and recipients are required")
            return render(request, 'userpanel/send_campaign.html', {'session': session})
        
        # Parse recipients (one phone number per line)
        recipient_list = [r.strip() for r in recipients.split('\n') if r.strip()]
        
        if not recipient_list:
            messages.error(request, "No valid recipients found")
            return render(request, 'userpanel/send_campaign.html', {'session': session})
        
        # Create campaign
        campaign = WASenderCampaign.objects.create(
            user=request.user,
            session=session,
            name=f"Campaign {timezone.now().strftime('%Y-%m-%d %H:%M')}",
            message_template=message,
            recipients=[{'phone': r} for r in recipient_list],
            total_recipients=len(recipient_list),
            status='running'
        )
        
        # Send messages
        service = WASenderService()
        sent_count = 0
        failed_count = 0
        
        for recipient in recipient_list:
            try:
                msg = service.send_text_message(session, recipient, message)
                if msg and msg.status == 'sent':
                    sent_count += 1
                else:
                    failed_count += 1
            except Exception as e:
                logger.error(f"Error sending to {recipient}: {e}")
                failed_count += 1
        
        # Update campaign stats
        campaign.messages_sent = sent_count
        campaign.messages_failed = failed_count
        campaign.status = 'completed'
        campaign.completed_at = timezone.now()
        campaign.save()
        
        messages.success(request, f"Campaign sent! {sent_count} successful, {failed_count} failed")
        return redirect('userpanel:whatsapp_dashboard')
    
    context = {
        'session': session,
    }
    
    return render(request, 'userpanel/send_campaign.html', context)


@login_required
@require_POST
def send_single_message(request):
    """
    AJAX endpoint to send single message
    """
    session = WASenderSession.objects.filter(
        user=request.user,
        status='connected'
    ).first()
    
    if not session:
        return JsonResponse({'error': 'No active session'}, status=400)
    
    data = json.loads(request.body)
    recipient = data.get('recipient', '').strip()
    message = data.get('message', '').strip()
    
    if not recipient or not message:
        return JsonResponse({'error': 'Recipient and message required'}, status=400)
    
    service = WASenderService()
    try:
        msg = service.send_text_message(session, recipient, message)
        if msg:
            return JsonResponse({
                'success': True,
                'message_id': msg.message_id,
                'status': msg.status
            })
        else:
            return JsonResponse({'error': 'Failed to send'}, status=500)
    except Exception as e:
        logger.error(f"Error sending message: {e}")
        return JsonResponse({'error': str(e)}, status=500)


# ==================== Webhook Handler ====================

@csrf_exempt
@require_POST
def wasender_webhook(request, user_id):
    """
    Webhook endpoint for WASender callbacks
    Receives message status updates and connection events
    """
    try:
        payload = json.loads(request.body)
        logger.info(f"Webhook received for user {user_id}: {payload}")
        
        service = WASenderService()
        service.process_webhook(payload)
        
        return JsonResponse({'status': 'ok'})
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return JsonResponse({'error': str(e)}, status=500)


# ==================== Campaign Management Views ====================

@login_required
def campaign_list(request):
    """
    List all campaigns
    """
    campaigns = WASenderCampaign.objects.filter(user=request.user).order_by('-created_at')
    
    context = {
        'campaigns': campaigns,
    }
    
    return render(request, 'userpanel/campaign_list.html', context)


@login_required
def campaign_detail(request, campaign_id):
    """
    Campaign detail and statistics
    """
    campaign = get_object_or_404(WASenderCampaign, id=campaign_id, user=request.user)
    
    # Get messages for this campaign
    messages_queryset = WASenderMessage.objects.filter(
        session=campaign.session,
        created_at__gte=campaign.created_at
    ).order_by('-created_at')
    
    context = {
        'campaign': campaign,
        'messages': messages_queryset,
    }
    
    return render(request, 'userpanel/campaign_detail.html', context)
