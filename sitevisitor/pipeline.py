from social_core.pipeline.partial import partial
from django.shortcuts import redirect
from django.urls import reverse
from .models import Profile, CustomUser
from django.contrib.auth import get_user_model

def associate_by_email(strategy, details, backend, user=None, *args, **kwargs):
    """
    Associate social account with existing user account if email matches.
    This ensures users who registered manually can login with Google using the same email.
    """
    if user:
        # Set flag to show welcome message on dashboard
        request = strategy.request
        request.session['show_social_welcome'] = True
        return {'is_new': False}  # User already exists and is authenticated
    
    # Get email from social provider
    email = details.get('email')
    if email:
        # Normalize email to lowercase
        email = email.lower()
        
        # Try to find existing user with this email
        User = get_user_model()
        try:
            existing_user = User.objects.get(email__iexact=email)
            
            # If user exists but email is not verified, verify it now
            if hasattr(existing_user, 'is_email_verified') and not existing_user.is_email_verified:
                existing_user.is_email_verified = True
                existing_user.save(update_fields=['is_email_verified'])
            
            # Set flag to show welcome message on dashboard
            request = strategy.request
            request.session['show_social_welcome'] = True
            
            # Return the existing user to associate with social account
            return {'user': existing_user, 'is_new': False}
        except User.DoesNotExist:
            pass  # No existing user found, continue with normal flow
    
    return {}

@partial
def require_whatsapp_number(strategy, details, user=None, is_new=False, *args, **kwargs):
    """
    Require the user to provide a WhatsApp number if they sign up with Google.
    This is a partial pipeline function that will redirect to a form if needed.
    """
    # If user is None, we can't proceed
    if user is None:
        return
    
    # Check if user already has a WhatsApp number
    from .models import WhatsAppNumber
    has_whatsapp = WhatsAppNumber.objects.filter(profile__user=user).exists()
    
    # If this is not a new user or user already has a WhatsApp number, continue
    if not is_new or has_whatsapp:
        return

    # Check if we're coming back from the form
    whatsapp_number = strategy.session_get('whatsapp_number', None)
    full_name = strategy.session_get('full_name', None)
    
    if whatsapp_number and full_name:
        try:
            # If we have the WhatsApp number in the session, save it to the user's profile
            profile, created = Profile.objects.get_or_create(user=user)
            
            # Update user's full name if provided
            if full_name and full_name.strip():
                user.full_name = full_name.strip()
                user.save(update_fields=['full_name'])
            
            # Create WhatsApp number for the user (avoid duplicates)
            whatsapp_obj, created = WhatsAppNumber.objects.get_or_create(
                profile=profile,
                defaults={
                    'number': whatsapp_number.lstrip('+'),  # Normalize by removing leading +
                    'is_primary': True,
                    'is_verified': False
                }
            )
            
            # If WhatsApp number already exists, update it
            if not created:
                whatsapp_obj.number = whatsapp_number.lstrip('+')
                whatsapp_obj.is_primary = True
                whatsapp_obj.save(update_fields=['number', 'is_primary'])
            
            # Clear the session data
            strategy.session_set('whatsapp_number', None)
            strategy.session_set('full_name', None)
            
            # Set flag to show welcome message on dashboard
            request = strategy.request
            request.session['show_social_welcome'] = True
            
            # Continue with the pipeline
            return
            
        except Exception as e:
            # Log the error and redirect back to form
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error saving WhatsApp number for user {user.email}: {str(e)}")
            
            from django.contrib import messages
            request = strategy.request
            messages.error(request, "There was an error saving your information. Please try again.")
            
            # Clear problematic session data and redirect back to form
            strategy.session_set('whatsapp_number', None)
            strategy.session_set('full_name', None)
            return redirect(reverse('sitevisitor:complete_social_signup'))
    else:
        # Store the partial pipeline data properly
        current_partial = kwargs.get('current_partial')
        if current_partial:
            strategy.session_set('partial_pipeline_token', current_partial.token)
        
        # Redirect to the form
        return redirect(reverse('sitevisitor:complete_social_signup'))