""" Django-Q Background Tasks for WhatsApp Campaign Sending
"""
import logging
import os
import time
import random
from datetime import timedelta
from django.utils import timezone
from django.conf import settings
from userpanel.models import WASenderCampaign, WASenderSession, WASenderMessage
from whatsappapi.models import Contact
from django.db.models import Q
from whatsappapi.wasender_service import WASenderService

logger = logging.getLogger(__name__)


def send_campaign_async(campaign_id):
    """
    Background task to send WhatsApp campaign messages
    
    Args:
        campaign_id: WASenderCampaign ID
    
    Returns:
        dict: Campaign results (sent_count, failed_count)
    """
    try:
        # Get campaign
        campaign = WASenderCampaign.objects.get(id=campaign_id)
        
        # Prevent duplicate execution - check if already running
        if campaign.status == 'running':
            # Check if it's been running for too long (stuck)
            if campaign.started_at and (timezone.now() - campaign.started_at) > timedelta(hours=1):
                logger.warning(f"Campaign {campaign_id} appears stuck, forcing completion")
                campaign.status = 'completed'
                campaign.completed_at = timezone.now()
                campaign.save()
                return {'status': 'completed', 'message': 'Campaign was stuck and has been completed'}
            else:
                logger.warning(f"DUPLICATE TASK DETECTED: Campaign {campaign_id} is already running, aborting duplicate execution")
                return {'status': 'already_running', 'message': 'Campaign is already running'}
        
        # CRITICAL: Atomically transition to running to prevent race conditions
        # This UPDATE will only succeed if status is NOT already 'running'
        from django.db import transaction
        with transaction.atomic():
            # Lock the row for update
            campaign_locked = WASenderCampaign.objects.select_for_update().get(id=campaign_id)
            
            # Double check status after lock
            if campaign_locked.status == 'running':
                logger.warning(f"RACE CONDITION PREVENTED: Campaign {campaign_id} already running after lock")
                return {'status': 'already_running', 'message': 'Campaign is already running'}
            
            # Set to running
            campaign_locked.status = 'running'
            campaign_locked.started_at = timezone.now()
            campaign_locked.save(update_fields=['status', 'started_at'])
        
        campaign.refresh_from_db()
        
        logger.info(f"Starting background campaign: {campaign.name} (ID: {campaign_id})")
        
        # Upload attachment if temp file exists (stored in attachment_url temporarily)
        temp_file_path = None
        original_filename = None
        
        # Check if attachment_url is a local file path (new campaigns) vs Cloudinary URL (old campaigns)
        if campaign.attachment_type and campaign.attachment_url:
            # If it's a local file path that exists, upload it
            if os.path.exists(campaign.attachment_url):
                temp_file_path = campaign.attachment_url
                original_filename = campaign.attachment_public_id or 'file'
                
                logger.info(f"Uploading attachment from temp: {temp_file_path}")
                
                try:
                    import cloudinary.uploader
                    
                    # Determine resource type
                    if campaign.attachment_type == 'image':
                        resource_type = 'image'
                    elif campaign.attachment_type in ['video', 'audio']:
                        resource_type = 'video'
                    else:
                        resource_type = 'raw'
                    
                    # Get clean filename without extension for public_id
                    clean_filename = os.path.splitext(original_filename)[0]
                    # Remove any special characters that might cause issues
                    clean_filename = clean_filename.replace(' ', '_')
                    
                    # Upload to Cloudinary from file path with original filename
                    with open(temp_file_path, 'rb') as f:
                        upload_result = cloudinary.uploader.upload(
                            f,
                            folder=f"wa_campaigns/{campaign.user.id}",
                            resource_type=resource_type,
                            type='upload',
                            access_mode='public',
                            public_id=clean_filename,  # Use original filename
                            use_filename=False,  # Don't use the temp file's UUID name
                            unique_filename=False,
                            overwrite=True
                        )
                    
                    # Update campaign with Cloudinary URL
                    campaign.attachment_url = upload_result['secure_url']
                    campaign.attachment_public_id = upload_result.get('public_id')
                    campaign.save(update_fields=['attachment_url', 'attachment_public_id'])
                    
                    logger.info(f"Attachment uploaded to Cloudinary: {campaign.attachment_url}")
                    
                    # Pre-upload to WASender if needed (for documents)
                    if campaign.attachment_type == 'document':
                        try:
                            import requests
                            head = requests.head(campaign.attachment_url, timeout=10, allow_redirects=True)
                            if head.status_code >= 400:
                                # Read file bytes
                                with open(temp_file_path, 'rb') as f:
                                    file_bytes = f.read()
                                
                                # Pre-upload to WASender
                                ws = WASenderService()
                                wasender_url = ws.upload_media_file(
                                    session=campaign.session,
                                    media_url=campaign.attachment_url,
                                    message_type='document',
                                    filename=original_filename,
                                    public_id=campaign.attachment_public_id,
                                    file_bytes=file_bytes
                                )
                                if wasender_url:
                                    campaign.wasender_document_url = wasender_url
                                    campaign.save(update_fields=['wasender_document_url'])
                                    logger.info(f"Document pre-uploaded to WASender: {wasender_url}")
                        except Exception as e:
                            logger.warning(f"WASender pre-upload failed: {e}")
                    
                    # Delete temp file
                    try:
                        os.remove(temp_file_path)
                        logger.info(f"Temp file deleted: {temp_file_path}")
                    except Exception as e:
                        logger.warning(f"Failed to delete temp file: {e}")
                        
                except Exception as e:
                    logger.error(f"Failed to upload attachment in background: {e}")
                    # Mark campaign as failed
                    campaign.status = 'failed'
                    campaign.save(update_fields=['status'])
                    return {'error': f'Attachment upload failed: {str(e)}'}
            else:
                # attachment_url is already a Cloudinary URL (old campaign), skip upload
                logger.info(f"Attachment already uploaded: {campaign.attachment_url}")
        
        # Get contacts from contact list
        contact_list = campaign.contact_list
        if not contact_list:
            logger.error(f"Campaign {campaign_id} has no contact list")
            campaign.status = 'failed'
            campaign.save()
            return {'error': 'No contact list'}
        
        # CRITICAL: Verify session is still connected before starting
        session = campaign.session
        if not session or session.status != 'connected':
            error_msg = f'Session not connected (status: {session.status if session else "None"})'
            logger.error(f"Campaign {campaign_id} session is not connected: {session.status if session else 'None'}")
            campaign.status = 'failed'
            campaign.save()
            return {'error': error_msg}
        
        # Initialize service and verify session status with WASender API
        service = WASenderService()
        try:
            service.get_session_status(session)
            session.refresh_from_db()
            if session.status != 'connected':
                logger.error(f"Campaign {campaign_id} session disconnected on WASender: {session.status}")
                campaign.status = 'failed'
                campaign.save()
                return {'error': f'Session disconnected on WASender (status: {session.status})'}
        except Exception as e:
            logger.error(f"Campaign {campaign_id} failed to verify session: {e}")
            campaign.status = 'failed'
            campaign.save()
            return {'error': f'Failed to verify session: {str(e)}'}
        
        # Get all contacts
        all_contacts = Contact.objects.filter(contact_list=contact_list)
        
        # Format all phone numbers and send (no filtering)
        contacts = []
        for contact in all_contacts:
            try:
                formatted_phone = service._format_phone_number(contact.phone_number or '')
                if formatted_phone:
                    contact.phone_formatted = formatted_phone
                    contacts.append(contact)
            except Exception as e:
                logger.warning(f"Contact {contact.id} phone format error: {e}")
        # Prefer verified WhatsApp contacts when available
        if contacts:
            whatsapp_verified = [c for c in contacts if c.is_on_whatsapp]
            if whatsapp_verified:
                logger.info(f"Campaign {campaign_id}: Using {len(whatsapp_verified)} verified WhatsApp contacts out of {len(contacts)}")
                contacts = whatsapp_verified
        
        if not contacts:
            logger.error(f"Contact list {contact_list.id} has no valid contacts (all {len(all_contacts)} contacts filtered)")
            campaign.status = 'completed'
            campaign.save()
            return {'sent_count': 0, 'failed_count': 0, 'invalid_count': len(invalid_contacts)}
        
        # Initialize counters
        sent_count = 0
        failed_count = 0
        session = campaign.session
        message_template = campaign.message_template
        
        # Get attachment URL if exists
        attachment_url = campaign.attachment_url
        attachment_type = campaign.attachment_type
        
        # Initialize recipients list with contact data (normalized E.164 phone numbers)
        campaign_recipients = []
        for contact in contacts:
            formatted_phone = service._format_phone_number(contact.phone_number or '')
            campaign_recipients.append({
                'phone': formatted_phone,
                'name': f"{contact.first_name or ''} {contact.last_name or ''}".strip()
            })
        
        # Update campaign with recipients list
        campaign.recipients = campaign_recipients
        campaign.save(update_fields=['recipients'])
        
        # Remove duplicate contacts based on phone number to prevent infinite loops
        unique_contacts = []
        seen_phones = set()
        for contact in contacts:
            phone_norm = service._format_phone_number(contact.phone_number or '')
            if phone_norm and phone_norm not in seen_phones:
                unique_contacts.append(contact)
                seen_phones.add(phone_norm)
        
        logger.info(f"Processing {len(unique_contacts)} unique contacts out of {len(contacts)} total contacts")
        
        # Initialize processed_phones tracking BEFORE batch or standard processing
        processed_phones = set()  # Track normalized phones we've already processed in this run
        
        # Batch processing logic
        if campaign.use_advanced_controls and campaign.batch_size_max > 0:
            # Split contacts into batches with random sizes
            batches = []
            remaining_contacts = unique_contacts.copy()
            
            while remaining_contacts:
                # Random batch size between min and max
                batch_size = random.randint(campaign.batch_size_min, campaign.batch_size_max)
                logger.info(f"📦 BATCH SIZE: {batch_size} contacts (Range: {campaign.batch_size_min}-{campaign.batch_size_max})")
                batch = remaining_contacts[:batch_size]
                batches.append(batch)
                remaining_contacts = remaining_contacts[batch_size:]
            
            logger.info(f"Campaign {campaign_id}: Split {len(unique_contacts)} contacts into {len(batches)} batches")
            
            # Process batches with cooldown
            total_sent = 0
            total_failed = 0
            
            for batch_index, batch in enumerate(batches, 1):
                logger.info(f"Campaign {campaign_id}: Processing batch {batch_index}/{len(batches)} ({len(batch)} contacts)")
                
                # Process contacts in this batch
                batch_sent, batch_failed = _process_contact_batch(
                    campaign, batch, service, session, message_template, 
                    attachment_url, attachment_type, processed_phones
                )
                
                total_sent += batch_sent
                total_failed += batch_failed
                
                # Update campaign progress
                campaign.messages_sent = total_sent
                campaign.messages_failed = total_failed
                campaign.save(update_fields=['messages_sent', 'messages_failed'])
                
                # Cooldown between batches (except after last batch)
                if batch_index < len(batches):
                    # Random cooldown in minutes
                    cooldown_minutes = random.uniform(
                        campaign.batch_cooldown_min, 
                        campaign.batch_cooldown_max
                    )
                    cooldown_seconds = int(cooldown_minutes * 60)
                    
                    logger.info(f"🧊 BATCH COOLDOWN: {cooldown_minutes:.1f} minutes ({cooldown_seconds}s) - Range: {campaign.batch_cooldown_min}-{campaign.batch_cooldown_max} min")
                    logger.info(f"⏸️ Waiting {cooldown_minutes:.1f} minutes before batch {batch_index + 1}...")
                    
                    # Sleep with pause checks
                    for _ in range(cooldown_seconds):
                        try:
                            campaign.refresh_from_db()
                            if campaign.status == 'paused':
                                logger.info(f"Campaign {campaign_id} paused during batch cooldown")
                                campaign.messages_sent = total_sent
                                campaign.messages_failed = total_failed
                                campaign.save(update_fields=['messages_sent', 'messages_failed'])
                                return {
                                    'campaign_id': campaign_id,
                                    'sent_count': total_sent,
                                    'failed_count': total_failed,
                                    'status': 'paused'
                                }
                        except Exception:
                            pass
                        time.sleep(1)
            
            # Mark campaign as completed after all batches
            campaign.status = 'completed'
            campaign.completed_at = timezone.now()
            campaign.messages_sent = total_sent
            campaign.messages_failed = total_failed
            campaign.save()
            
            logger.info(f"Campaign {campaign.name} completed: {total_sent} sent, {total_failed} failed")
            
            return {
                'campaign_id': campaign_id,
                'sent_count': total_sent,
                'failed_count': total_failed,
                'status': 'completed'
            }
        
        # Standard processing (no batching) - original logic below
        
        # Process each unique contact with safety limit to prevent infinite loops
        max_iterations = len(unique_contacts) * 2  # Safety limit: at most 2x the unique contacts
        iteration_count = 0
        
        for contact in unique_contacts:
            # Check for cancel/pause request
            try:
                campaign.refresh_from_db()
                if campaign.status == 'paused':
                    logger.info(f"Campaign {campaign_id} paused by user. Halting sends.")
                    break
            except Exception:
                pass
            
            # Format phone number once
            phone_norm = service._format_phone_number(contact.phone_number or '')
            
            # Safety check to prevent infinite loops
            iteration_count += 1
            if iteration_count > max_iterations:
                logger.error(f"Safety limit exceeded: {iteration_count} iterations for {len(unique_contacts)} contacts")
                break
            
            # Skip if we've already processed this phone in this campaign run
            if phone_norm in processed_phones:
                logger.warning(f"Skipping duplicate phone {phone_norm} in current campaign run")
                continue
                
            try:
                # Mark as processed to prevent duplicate sends in same run
                processed_phones.add(phone_norm)
                
                # CRITICAL: Campaign-specific duplicate prevention
                # Check 1: Message already sent for this EXACT campaign (most important)
                existing_campaign_msg = WASenderMessage.objects.filter(
                    session=session,
                    recipient=phone_norm,
                    metadata__campaign_id=campaign.id
                ).first()
                
                if existing_campaign_msg:
                    logger.warning(f"DUPLICATE PREVENTED: Message already exists for {phone_norm} in campaign {campaign.id}")
                    continue
                
                # Check 2: REMOVED - No longer blocking based on time across sessions
                # Different sessions (different WhatsApp numbers) SHOULD be able to send to same recipient
                # Only prevent duplicates within the SAME campaign
                
                # Personalize message using dynamic fields
                personalized_message = message_template
                
                # Replace variables from contact.fields (dynamic JSON field)
                if contact.fields:
                    for field_name, field_value in contact.fields.items():
                        placeholder = f"{{{field_name}}}"
                        personalized_message = personalized_message.replace(
                            placeholder, 
                            str(field_value) if field_value else ''
                        )
                
                # Also support legacy field replacements
                personalized_message = personalized_message.replace('{first_name}', contact.first_name or '')
                personalized_message = personalized_message.replace('{last_name}', contact.last_name or '')
                personalized_message = personalized_message.replace('{phone}', contact.phone_number or '')
                personalized_message = personalized_message.replace('{email}', contact.email or '')
                personalized_message = personalized_message.replace('{custom_field_1}', contact.custom_field_1 or '')
                personalized_message = personalized_message.replace('{custom_field_2}', contact.custom_field_2 or '')
                personalized_message = personalized_message.replace('{custom_field_3}', contact.custom_field_3 or '')
                
                # Send message with or without attachment
                msg = None
                if attachment_url and attachment_type:
                    # Check pause before sending attachment
                    try:
                        campaign.refresh_from_db()
                        if campaign.status == 'paused':
                            logger.info(f"Campaign {campaign_id} paused by user. Halting sends before attachment.")
                            break
                    except Exception:
                        pass
                    
                    # Special handling: for audio, send text first, then audio media
                    if attachment_type == 'audio':
                        # 1) Send text message to guarantee content delivery
                        text_msg = service.send_text_message(session, phone_norm, personalized_message)
                        if text_msg:
                            try:
                                current_meta = text_msg.metadata or {}
                                current_meta.update({'campaign_id': campaign.id})
                                text_msg.metadata = current_meta
                                text_msg.save(update_fields=['metadata'])
                            except Exception as e:
                                logger.warning(f"Unable to tag text message {getattr(text_msg, 'id', '?')} with campaign_id: {e}")
                            if text_msg.status == 'sent':
                                sent_count += 1
                            else:
                                failed_count += 1
                        else:
                            failed_count += 1
                            # Record failed text message
                            try:
                                WASenderMessage.objects.create(
                                    session=session,
                                    user=session.user,
                                    recipient=phone_norm,
                                    message_type='text',
                                    content=personalized_message,
                                    status='failed',
                                    error_message='Text send failed before audio',
                                    metadata={'campaign_id': campaign.id}
                                )
                            except Exception as e:
                                logger.error(f"Failed to record failed text message for {phone_norm}: {e}")

                        # 2) Then send audio media (caption often not shown for audio)
                        media_to_send = attachment_url
                        msg = service.send_media_message(
                            session=session,
                            recipient=phone_norm,
                            media_url=media_to_send,
                            message_type='audio',
                            caption=None
                        )
                    else:
                        # Prefer Wasender-hosted URL if available for documents
                        media_to_send = attachment_url
                        if attachment_type == 'document' and getattr(campaign, 'wasender_document_url', None):
                            media_to_send = campaign.wasender_document_url
                        # Send media message with caption
                        msg = service.send_media_message(
                            session=session,
                            recipient=phone_norm,
                            media_url=media_to_send,
                            message_type=attachment_type,
                            caption=personalized_message
                        )
                else:
                    # Check pause before sending text message
                    try:
                        campaign.refresh_from_db()
                        if campaign.status == 'paused':
                            logger.info(f"Campaign {campaign_id} paused by user. Halting sends before text.")
                            break
                    except Exception:
                        pass
                    
                    # Send text-only message
                    msg = service.send_text_message(session, phone_norm, personalized_message)
                
                # Update counters and tag messages with campaign id metadata
                if msg:
                    try:
                        current_meta = msg.metadata or {}
                        current_meta.update({'campaign_id': campaign.id})
                        msg.metadata = current_meta
                        msg.save(update_fields=['metadata'])
                    except Exception as e:
                        logger.warning(f"Unable to tag message {getattr(msg, 'id', '?')} with campaign_id: {e}")
                    if msg.status == 'sent':
                        sent_count += 1
                        logger.info(f"✅ Message sent successfully to {phone_norm}")
                    else:
                        failed_count += 1
                        error_msg = getattr(msg, 'error_message', 'Unknown error')
                        logger.error(f"❌ Message failed to {phone_norm}: status={msg.status}, error={error_msg}")
                else:
                    failed_count += 1
                    logger.error(f"❌ No message object returned for {phone_norm} - send_text_message returned None")
                    # Record failed message for visibility in campaign details and exports
                    try:
                        WASenderMessage.objects.create(
                            session=session,
                            user=session.user,
                            recipient=phone_norm,
                            message_type=attachment_type or 'text',
                            content=attachment_url or personalized_message,
                            caption=personalized_message if attachment_url and attachment_type else None,
                            status='failed',
                            error_message='Send method returned None - possible API error or rate limit',
                            metadata={'campaign_id': campaign.id}
                        )
                    except Exception as e:
                        logger.error(f"Failed to record failed message for {phone_norm}: {e}")
                
                # Update campaign progress in real-time
                campaign.messages_sent = sent_count
                campaign.messages_failed = failed_count
                campaign.save()
                
                # Add delay based on account protection setting with pause check
                # Use advanced controls if enabled, otherwise use standard delay
                if campaign.use_advanced_controls:
                    # Random delay between min and max
                    delay = random.randint(campaign.random_delay_min, campaign.random_delay_max)
                    logger.info(f"⏱️ ADVANCED DELAY: {delay}s (Range: {campaign.random_delay_min}-{campaign.random_delay_max}s)")
                else:
                    # Standard delay from settings
                    delay = settings.MESSAGE_DELAY_WITH_PROTECTION if session.account_protection_enabled else settings.MESSAGE_DELAY_WITHOUT_PROTECTION
                    logger.info(f"⏱️ STANDARD DELAY: {delay}s (Protection: {session.account_protection_enabled})")
                
                # Sleep in intervals so we can check for pause status
                # Only refresh every 10 seconds to reduce database queries
                pause_check_interval = 10  # Check pause status every 10 seconds
                checked_at = 0
                
                for second in range(delay):
                    checked_at += 1
                    
                    # Check pause status less frequently (every 10 seconds)
                    if checked_at >= pause_check_interval:
                        try:
                            campaign.refresh_from_db()
                            if campaign.status == 'paused':
                                logger.info(f"Campaign {campaign_id} paused during delay. Halting sends.")
                                break
                        except Exception:
                            pass
                        checked_at = 0
                    
                    time.sleep(1)
                
            except Exception as e:
                logger.error(f"Error sending to {contact.phone_number}: {e}")
                failed_count += 1
                campaign.messages_failed = failed_count
                campaign.save()
        
        # If paused, keep status and return partial results
        campaign.refresh_from_db()
        if campaign.status == 'paused':
            logger.info(f"Campaign {campaign.name} paused: {sent_count} sent, {failed_count} failed")
            # IMPORTANT: Do NOT change status back from paused - keep it paused
            campaign.messages_sent = sent_count
            campaign.messages_failed = failed_count
            campaign.save(update_fields=['messages_sent', 'messages_failed'])
            return {
                'campaign_id': campaign_id,
                'sent_count': sent_count,
                'failed_count': failed_count,
                'status': 'paused'
            }
        
        # Mark campaign as completed (only if NOT paused)
        campaign.status = 'completed'
        campaign.completed_at = timezone.now()
        campaign.messages_sent = sent_count
        campaign.messages_failed = failed_count
        campaign.save()
        
        logger.info(f"Campaign {campaign.name} completed: {sent_count} sent, {failed_count} failed")
        
        return {
            'campaign_id': campaign_id,
            'sent_count': sent_count,
            'failed_count': failed_count,
            'status': 'completed'
        }
        
    except WASenderCampaign.DoesNotExist:
        logger.error(f"Campaign {campaign_id} not found")
        return {'error': 'Campaign not found'}
    
    except Exception as e:
        logger.error(f"Campaign {campaign_id} failed with error: {e}")
        try:
            campaign = WASenderCampaign.objects.get(id=campaign_id)
            campaign.status = 'failed'
            campaign.save()
        except:
            pass
        return {'error': str(e)}


def _process_contact_batch(campaign, batch_contacts, service, session, message_template, 
                           attachment_url, attachment_type, processed_phones):
    """
    Helper function to process a batch of contacts
    Returns tuple: (sent_count, failed_count)
    """
    sent_count = 0
    failed_count = 0
    
    for contact in batch_contacts:
        # Check for pause request
        try:
            campaign.refresh_from_db()
            if campaign.status == 'paused':
                logger.info(f"Campaign {campaign.id} paused during batch processing")
                break
        except Exception:
            pass
        
        # Format phone number
        phone_norm = service._format_phone_number(contact.phone_number or '')
        
        # Skip if already processed
        if phone_norm in processed_phones:
            continue
        
        try:
            # Mark as processed
            processed_phones.add(phone_norm)
            
            # Check for existing campaign message
            existing_campaign_msg = WASenderMessage.objects.filter(
                session=session,
                recipient=phone_norm,
                metadata__campaign_id=campaign.id
            ).first()
            
            if existing_campaign_msg:
                logger.warning(f"DUPLICATE PREVENTED: Message already exists for {phone_norm} in campaign {campaign.id}")
                continue
            
            # Personalize message
            personalized_message = message_template
            
            # Replace variables from contact.fields
            if contact.fields:
                for field_name, field_value in contact.fields.items():
                    placeholder = f"{{{field_name}}}"
                    personalized_message = personalized_message.replace(
                        placeholder, 
                        str(field_value) if field_value else ''
                    )
            
            # Legacy field replacements
            personalized_message = personalized_message.replace('{first_name}', contact.first_name or '')
            personalized_message = personalized_message.replace('{last_name}', contact.last_name or '')
            personalized_message = personalized_message.replace('{phone}', contact.phone_number or '')
            personalized_message = personalized_message.replace('{email}', contact.email or '')
            personalized_message = personalized_message.replace('{custom_field_1}', contact.custom_field_1 or '')
            personalized_message = personalized_message.replace('{custom_field_2}', contact.custom_field_2 or '')
            personalized_message = personalized_message.replace('{custom_field_3}', contact.custom_field_3 or '')
            
            # Send message
            msg = None
            if attachment_url and attachment_type:
                if attachment_type == 'audio':
                    # Send text first, then audio
                    text_msg = service.send_text_message(session, phone_norm, personalized_message)
                    if text_msg:
                        try:
                            current_meta = text_msg.metadata or {}
                            current_meta.update({'campaign_id': campaign.id})
                            text_msg.metadata = current_meta
                            text_msg.save(update_fields=['metadata'])
                        except Exception as e:
                            logger.warning(f"Unable to tag text message: {e}")
                        if text_msg.status == 'sent':
                            sent_count += 1
                        else:
                            failed_count += 1
                    else:
                        failed_count += 1
                    
                    # Send audio
                    msg = service.send_media_message(
                        session=session,
                        recipient=phone_norm,
                        media_url=attachment_url,
                        message_type='audio',
                        caption=None
                    )
                else:
                    # Send media with caption
                    media_to_send = attachment_url
                    if attachment_type == 'document' and getattr(campaign, 'wasender_document_url', None):
                        media_to_send = campaign.wasender_document_url
                    
                    msg = service.send_media_message(
                        session=session,
                        recipient=phone_norm,
                        media_url=media_to_send,
                        message_type=attachment_type,
                        caption=personalized_message
                    )
            else:
                # Send text message only
                msg = service.send_text_message(session, phone_norm, personalized_message)
            
            # Update counters
            if msg:
                try:
                    current_meta = msg.metadata or {}
                    current_meta.update({'campaign_id': campaign.id})
                    msg.metadata = current_meta
                    msg.save(update_fields=['metadata'])
                except Exception as e:
                    logger.warning(f"Unable to tag message {getattr(msg, 'id', '?')} with campaign_id: {e}")
                
                if msg.status == 'sent':
                    sent_count += 1
                    logger.info(f"✅ Message sent successfully to {phone_norm}")
                else:
                    failed_count += 1
                    error_msg = getattr(msg, 'error_message', 'Unknown error')
                    logger.error(f"❌ Message failed to {phone_norm}: status={msg.status}, error={error_msg}")
            else:
                failed_count += 1
                logger.error(f"❌ No message object returned for {phone_norm}")
                # Record failed message
                try:
                    WASenderMessage.objects.create(
                        session=session,
                        user=session.user,
                        recipient=phone_norm,
                        message_type=attachment_type or 'text',
                        content=attachment_url or personalized_message,
                        caption=personalized_message if attachment_url and attachment_type else None,
                        status='failed',
                        error_message='Send method returned None - possible API error or rate limit',
                        metadata={'campaign_id': campaign.id}
                    )
                except Exception as e:
                    logger.error(f"Failed to record failed message for {phone_norm}: {e}")
            
            # Random delay with pause checks
            if campaign.use_advanced_controls:
                delay = random.randint(campaign.random_delay_min, campaign.random_delay_max)
                logger.info(f"⏱️ Message delay: {delay}s (Range: {campaign.random_delay_min}-{campaign.random_delay_max}s)")
            else:
                delay = settings.MESSAGE_DELAY_WITH_PROTECTION if session.account_protection_enabled else settings.MESSAGE_DELAY_WITHOUT_PROTECTION
            
            for _ in range(delay):
                try:
                    campaign.refresh_from_db()
                    if campaign.status == 'paused':
                        logger.info(f"Campaign {campaign.id} paused during delay")
                        break
                except Exception:
                    pass
                time.sleep(1)
                
        except Exception as e:
            logger.error(f"Error sending to {contact.phone_number}: {e}")
            failed_count += 1
    
    return sent_count, failed_count
