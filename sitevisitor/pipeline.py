from social_core.pipeline.partial import partial
from django.shortcuts import redirect
from django.urls import reverse
from .models import Profile, CustomUser
from django.contrib.auth import get_user_model
from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse


def block_permanently_blocked(strategy, details, backend, user=None, *args, **kwargs):
    """
    Early social-auth pipeline guard: prevent login if the matched account
    is permanently blocked by admin. Works for existing users matched by email.
    """
    email = details.get('email')
    if not email:
        return {}

    User = get_user_model()
    try:
        existing_user = User.objects.get(email__iexact=email.lower())
        from whatsappapi.models import UserModerationProfile
        mp, _ = UserModerationProfile.objects.get_or_create(user=existing_user)
        if mp and mp.permanently_blocked and not (existing_user.is_staff or existing_user.is_superuser):
            # Interrupt pipeline with a friendly redirect back to login
            return redirect('/login/?social_auth_error=blocked_by_admin')
    except User.DoesNotExist:
        pass

    return {}

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
    Collect full_name when user signs up with Google.
    WhatsApp number will be added later from the user panel after signup.
    """
    # If user is None, we can't proceed
    if user is None:
        return
    
    # If this is not a new user, continue
    if not is_new:
        return

    # Check if we're coming back from the form
    full_name = strategy.session_get('full_name', None)
    
    if full_name:
        try:
            # Update user's full name if provided
            if full_name and full_name.strip():
                user.full_name = full_name.strip()
                user.save(update_fields=['full_name'])
            
            # Ensure user has a profile
            profile, created = Profile.objects.get_or_create(user=user)
            
            # Clear the session data
            strategy.session_set('full_name', None)
            strategy.session_set('partial_pipeline_token', None)
            
            # Set flag to show welcome message on dashboard
            request = strategy.request
            request.session['show_social_welcome'] = True
            
            # Continue with the pipeline
            return
            
        except Exception as e:
            # Log the error and redirect back to form
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error saving user full_name for user {user.email}: {str(e)}")
            
            from django.contrib import messages
            request = strategy.request
            messages.error(request, "There was an error saving your information. Please try again.")
            
            # Clear problematic session data and redirect back to form
            strategy.session_set('full_name', None)
            return redirect(reverse('sitevisitor:complete_social_signup'))
    else:
        # Store the partial pipeline data properly
        current_partial = kwargs.get('current_partial')
        if current_partial:
            strategy.session_set('partial_pipeline_token', current_partial.token)
        
        # Redirect to the form
        return redirect(reverse('sitevisitor:complete_social_signup'))