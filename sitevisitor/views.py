from django.shortcuts import render, get_object_or_404, redirect
import uuid
import datetime
from django.contrib.auth import authenticate, login, logout, get_user_model
from whatsappapi.models import UserModerationProfile
from django.contrib import messages
from django.utils import timezone
from django.urls import reverse_lazy, reverse
from django.core.mail import send_mail
from smtplib import SMTPException
from django.conf import settings
from django.template.loader import render_to_string
from django.db import IntegrityError
from django.contrib.auth.decorators import login_required
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.http import Http404, HttpResponseForbidden, HttpResponseBadRequest
from functools import wraps

from .forms import LoginForm, SignupForm, CustomPasswordResetForm, CustomSetPasswordForm, OTPVerificationForm, NewsletterForm, ContactForm
from .models import CustomUser, Profile, EmailVerification, PasswordReset, OTPVerification, NewsletterSubscriber, ContactMessage
from adminpanel.models import SubscriptionPlan
from .indexnow import notify_page_update


# --- Static Page Views (Unchanged) --- #
from django.views.decorators.cache import cache_page
from django.core.cache import cache

@cache_page(600)  # Cache for 10 minutes
def IndexView(request):
    # Use cached form for anonymous users
    if not request.user.is_authenticated:
        newsletter_form = NewsletterForm()
    else:
        newsletter_form = NewsletterForm()
    
    # Cache subscription plans for 30 minutes
    plans = cache.get('subscription_plans')
    if plans is None:
        plans = list(SubscriptionPlan.objects.filter(is_active=True).order_by('price').values('id', 'name', 'price', 'duration_days', 'features'))
        cache.set('subscription_plans', plans, 1800)  # 30 minutes
    
    context = {
        'newsletter_form': newsletter_form,
        'plans': plans,
    }
    return render(request, 'sitevisitor/home.html', context)

def contact(request):
    if request.method == 'POST':
        form = ContactForm(request.POST)
        if form.is_valid():
            name = form.cleaned_data['name']
            email = form.cleaned_data['email']
            subject = form.cleaned_data['subject']
            message = form.cleaned_data['message']

            # Save the message to the database
            ContactMessage.objects.create(
                name=form.cleaned_data['name'],
                email=form.cleaned_data['email'],
                subject=form.cleaned_data['subject'],
                message=form.cleaned_data['message']
            )

            # Send email with error handling
            try:
                send_mail(
                    f'Contact Form Submission: {subject}',
                    f'Name: {name}\nEmail: {email}\n\nMessage:\n{message}',
                    settings.DEFAULT_FROM_EMAIL,  # Sender's email (from settings)
                    ['hi@wacampaignsender.com'],    # Recipient's email
                    fail_silently=False,
                )
            except SMTPException as e:
                # Handle SMTP errors (redirect already imported at top)
                if 'authentication failed' in str(e).lower():
                    return redirect(reverse('sitevisitor:error_email') + '?type=invalid_api_key')
                elif 'quota' in str(e).lower() or 'limit' in str(e).lower():
                    return redirect(reverse('sitevisitor:error_email') + '?type=quota_exceeded')
                else:
                    return redirect(reverse('sitevisitor:error_email') + '?type=general')
            except Exception as e:
                # Handle other email errors
                messages.error(request, 'Unable to send your message at this time. Please try again later.')
                return render(request, 'sitevisitor/contact.html', {'form': form})

            messages.success(request, 'Your message has been sent successfully! We will get back to you shortly.')
            # Notify search engines about contact page activity
            notify_page_update('/contact/')
            return redirect('sitevisitor:contact')
    else:
        form = ContactForm()

    return render(request, 'sitevisitor/contact.html', {'form': form})

@cache_page(1800)  # Cache for 30 minutes
def blogs(request):
    context = {
        'posts': ALL_BLOG_POSTS
    }
    return render(request, 'sitevisitor/blogs.html', context)

# Shared context for all blog posts to populate the sidebar
ALL_BLOG_POSTS = [
    {
        'title': 'Direct WhatsApp Outreach: Powerful & Simple',
        'url_name': 'blog_post_direct_outreach',
        'slug': 'direct-whatsapp-outreach',
        'image': 'image/post_direct_outreach_optimized.jpg',
        'description': 'Discover how WA Campaign Sender dashboard makes WhatsApp marketing effortless. Send targeted campaigns without technical complexity or maintenance headaches.'
    },
    {
        'title': 'Sending Bulk WhatsApp Messages Safely',
        'url_name': 'blog_post_safe_sending',
        'slug': 'sending-bulk-whatsapp-safely',
        'image': 'image/blog_safe_sending_optimized.jpg',
        'description': 'Learn essential best practices for sending bulk WhatsApp messages without risking your account. Prioritize safety and maintain a healthy sender reputation...'
    },
    {
        'title': 'Personalization Power: Crafting Messages That Convert',
        'url_name': 'blog_post_easy_personalization',
        'slug': 'personalization-power-crafting-messages-that-convert',
        'image': 'image/post_personalization_optimized.jpg',
        'description': 'Elevate your WhatsApp campaigns with effective personalization, directly from your browser. Learn how to make a genuine impact and build stronger customer connections.'
    },
    {
        'title': 'Beyond Spreadsheets: Contact Management',
        'url_name': 'blog_post_contact_management',
        'slug': 'contact-management-beyond-spreadsheets',
        'image': 'image/post_contact_management_optimized.jpg',
        'description': 'Discover how to build and manage contact lists directly in WhatsApp using CSV imports and the powerful one-click Contact Extractor.'
    },
    {
        'title': 'Unlocking WhatsApp for Events',
        'url_name': 'blog_post_event_marketing',
        'slug': 'event-marketing-invitations-reminders',
        'image': 'image/blog_event_marketing_optimized.jpg',
        'description': 'Use WA Campaign Sender to manage event communications like invitations, reminders, and updates efficiently...'
    },
    {
        'title': 'The Ultimate WhatsApp Campaign Checklist',
        'url_name': 'blog_post_campaign_checklist',
        'slug': 'campaign-checklist-successful-whatsapp',
        'image': 'image/blog_campaign_checklist_optimized.jpg',
        'description': 'A step-by-step guide to planning and executing effective WhatsApp campaigns with WA Campaign Sender...'
    },
    {
        'title': 'Avoiding the WhatsApp Ban Hammer',
        'url_name': 'blog_post_advanced_safety',
        'slug': 'advanced-safety-avoiding-ban-hammer',
        'image': 'image/blog_advanced_safety_optimized.jpg',
        'description': 'Delve into advanced safety tactics, understanding WhatsApp\'s ecosystem, and responsible use of WA Campaign Sender...'
    },
    {
        'title': 'Enterprise Grade: Professional WhatsApp Solutions',
        'url_name': 'blog_post_extension_power',
        'slug': 'enterprise-whatsapp-solutions',
        'image': 'image/blog_extension_power_optimized.jpg',
        'description': 'Discover enterprise-grade WhatsApp integration with superior stability and reliability. WA Campaign Sender handles the complexity so you focus on results.'
    },
    {
        'title': 'Maximize Your Reach: Timing & Frequency',
        'url_name': 'blog_post_timing_frequency',
        'slug': 'timing-frequency-maximizing-reach',
        'image': 'image/blog_timing_frequency_optimized.jpg',
        'description': 'Learn the art and science of scheduling your campaigns. Find the best times to send messages and the right frequency to avoid spamming.'
    },
]

def blog_post_direct_outreach(request):
    context = {
        'posts': ALL_BLOG_POSTS,
        'current_slug': 'direct-whatsapp-outreach'
    }
    return render(request, 'sitevisitor/blog/post_direct_outreach.html', context)

def blog_post_safe_sending(request):
    context = {
        'posts': ALL_BLOG_POSTS,
        'current_slug': 'sending-bulk-whatsapp-safely'
    }
    return render(request, 'sitevisitor/blog/post_safe_sending.html', context)

def blog_post_contact_management(request):
    context = {
        'posts': ALL_BLOG_POSTS,
        'current_slug': 'contact-management-beyond-spreadsheets'
    }
    return render(request, 'sitevisitor/blog/post_contact_management.html', context)

def blog_post_easy_personalization(request):
    context = {
        'posts': ALL_BLOG_POSTS,
        'current_slug': 'personalization-power-crafting-messages-that-convert'
    }
    return render(request, 'sitevisitor/blog/post_easy_personalization.html', context)

def blog_post_event_marketing(request):
    context = {
        'posts': ALL_BLOG_POSTS,
        'current_slug': 'event-marketing-invitations-reminders'
    }
    return render(request, 'sitevisitor/blog/post_event_marketing.html', context)

def blog_post_campaign_checklist(request):
    context = {
        'posts': ALL_BLOG_POSTS,
        'current_slug': 'campaign-checklist-successful-whatsapp'
    }
    return render(request, 'sitevisitor/blog/post_campaign_checklist.html', context)

def blog_post_advanced_safety(request):
    context = {
        'posts': ALL_BLOG_POSTS,
        'current_slug': 'advanced-safety-avoiding-ban-hammer'
    }
    return render(request, 'sitevisitor/blog/post_advanced_safety.html', context)

def blog_post_extension_power(request):
    context = {
        'posts': ALL_BLOG_POSTS,
        'current_slug': 'enterprise-whatsapp-solutions'
    }
    return render(request, 'sitevisitor/blog/post_extension_power.html', context)

def blog_post_timing_frequency(request):
    context = {
        'posts': ALL_BLOG_POSTS,
        'current_slug': 'timing-frequency-maximizing-reach'
    }
    return render(request, 'sitevisitor/blog/post_timing_frequency.html', context)
    
def PrivacyView(request):
    # Placeholder - implement actual privacy policy page or template
    return render(request, 'sitevisitor/privacy.html') # Assuming a privacy.html template

def TermsView(request):
    # Placeholder - implement actual terms of service page or template
    return render(request, 'sitevisitor/terms.html') # Assuming a terms.html template

def RefundView(request):
    # Placeholder - implement actual refund policy page or template
    return render(request, 'sitevisitor/refund.html') # Assuming a refund.html template

def FaqView(request):
    return render(request, 'sitevisitor/faqs.html')

def AboutView(request):
    return render(request, 'sitevisitor/about.html')

def PricingView(request):
    from adminpanel.models import SubscriptionPlan
    plans = SubscriptionPlan.objects.filter(is_active=True).order_by('price')
    context = {'plans': plans}
    return render(request, 'sitevisitor/pricing.html', context)

# --- Authentication Views (Refactored to FBV) --- #
def login_view(request):
    template_name = 'sitevisitor/login.html'
    form_class = LoginForm
    
    # Handle social auth errors
    social_error = request.GET.get('social_auth_error', None)
    if social_error:
        if social_error == 'blocked_by_admin':
            messages.error(request, 'Your login is blocked by admin. Contact support.')
        else:
            messages.error(request, f'Social authentication error: {social_error}')

    if request.user.is_authenticated:
        if request.user.is_staff or request.user.is_superuser:
            return redirect('admin_panel:dashboard')
        return redirect('userpanel:dashboard')

    if request.method == 'POST':
        form = form_class(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            password = form.cleaned_data['password']
            remember_me = form.cleaned_data.get('remember_me', False)
            

            user = authenticate(request, email=email, password=password)

            if user is not None:
                # Check if email verification is required and if email is verified
                # This assumes your CustomUser model has an 'is_email_verified' field.
                # Adjust if your field name is different or if this check is not needed.
                if hasattr(user, 'is_email_verified') and not user.is_email_verified:
                    messages.error(request, 'Please verify your email before logging in.')
                    return render(request, template_name, {'form': form})
                # Check admin block
                try:
                    mp, _ = UserModerationProfile.objects.get_or_create(user=user)
                except Exception:
                    mp = None
                if mp and mp.permanently_blocked:
                    messages.error(request, 'Your login is blocked by admin. Contact support.')
                    return render(request, template_name, {'form': form})

                login(request, user)
                
                if remember_me:
                    # Uses default SESSION_COOKIE_AGE from settings if not overridden
                    request.session.set_expiry(settings.SESSION_COOKIE_AGE) 
                else:
                    request.session.set_expiry(0)  # Session expires when browser closes
                
                messages.success(request, f'Welcome back, {user.full_name}!')
                
                next_url = request.GET.get('next')
                if next_url:
                    return redirect(next_url)
                if user.is_staff or user.is_superuser:
                    return redirect('admin_panel:dashboard')
                return redirect('userpanel:dashboard')
            else:
                messages.error(request, 'Invalid email or password. Please try again.')
        else:
            # Form is not valid, errors will be displayed by the template
            # You can add a generic message here if you want, but field-specific errors are usually better
            pass # messages.error(request, 'Please correct the errors below.')
    else:
        form = form_class() # For GET request, show an empty form
    
    return render(request, template_name, {'form': form})

def _send_verification_email_util(request, user, token):
    try:
        verification_url = request.build_absolute_uri(
            reverse('sitevisitor:verify_email', kwargs={'token': token})
        )
        # Get expiry days from settings, with a default of 2
        expiry_days = getattr(settings, 'EMAIL_VERIFICATION_EXPIRY_DAYS', 2)
        
        subject = 'Verify your WA Campaign Sender account'
        message_html = render_to_string('sitevisitor/emails/email_verification.html', {
            'user': user,
            'verification_url': verification_url,
            'expiry_days': expiry_days, # Pass expiry days to the template
        })
        send_mail(
            subject,
            # Provide a plain text alternative for email clients that don't render HTML
            f"""Hi there,\n\nPlease click the link to verify your email address: {verification_url}\n\nThis link will expire in {expiry_days} days.""",
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=False,
            html_message=message_html
        )
    except SMTPException as e:
        # Handle SMTP errors
        if 'authentication failed' in str(e).lower():
            return redirect(reverse('sitevisitor:error_email') + '?type=invalid_api_key')
        elif 'quota' in str(e).lower() or 'limit' in str(e).lower():
            return redirect(reverse('sitevisitor:error_email') + '?type=quota_exceeded')
        else:
            return redirect(reverse('sitevisitor:error_email') + '?type=general')
    except Exception as e:
        # Handle other email errors
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f'Email sending error: {str(e)}')
        return redirect(reverse('sitevisitor:error_email') + '?type=general')
    return None

def signup_view(request):
    template_name = 'sitevisitor/signup.html'
    form_class = SignupForm
    if request.user.is_authenticated:
        return redirect('sitevisitor:home')

    if request.method == 'POST':
        form = form_class(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.is_active = True # Users are active by default but email not verified
            user.is_email_verified = False
            try:
                user.save()
            except IntegrityError:
                messages.error(request, 'An account with this email already exists.')
                return render(request, template_name, {'form': form})
            
            # ... existing code ...
            token = str(uuid.uuid4())
            expiry = timezone.now() + datetime.timedelta(days=getattr(settings, 'EMAIL_VERIFICATION_EXPIRY_DAYS', 2))
            EmailVerification.objects.create(user=user, token=token, expires_at=expiry)
            
            _send_verification_email_util(request, user, token)
            
            messages.success(request, 'Registration successful! Please check your email to verify your account.')
            # Instead of redirecting to login, render the 'check your email' page.
            # The user's email can be passed to the template if needed, e.g., for display.
            return render(request, 'sitevisitor/email_verification.html', {'email': user.email})
    else:
        form = form_class()
    return render(request, template_name, {'form': form})

def email_verification_view(request, token):
    try:
        verification = EmailVerification.objects.get(token=token)
        if verification.expires_at < timezone.now():
            messages.error(request, 'Verification link has expired. Please request a new one.')
            # Optionally, delete expired token: verification.delete()
            return redirect('sitevisitor:login') # Or a page to resend verification

        user = verification.user
        if user.is_email_verified and user.is_active:
            messages.info(request, 'Account already active and email verified. You can log in.')
        else:
            user.is_email_verified = True
            user.is_active = True  # Explicitly ensure user is active
            user.save(update_fields=['is_email_verified', 'is_active'])
            messages.success(request, 'Email verified successfully! Your account is now active. You can log in.')
        verification.delete()  # Delete token after successful verification or if already verified
        return redirect('sitevisitor:login')
    except EmailVerification.DoesNotExist:
        messages.error(request, 'Invalid verification link.')
        return redirect('sitevisitor:login')


@login_required
def resend_verification_view(request):
    if request.user.is_email_verified:
        messages.info(request, 'Your email is already verified.')
        return redirect('sitevisitor:home') # Or wherever verified users should go

    # Delete any existing tokens for the user to prevent multiple active tokens
    EmailVerification.objects.filter(user=request.user).delete()
    
    token = str(uuid.uuid4())
    expiry = timezone.now() + datetime.timedelta(days=settings.EMAIL_VERIFICATION_EXPIRY_DAYS or 2)
    EmailVerification.objects.create(user=request.user, token=token, expires_at=expiry)
    
    _send_verification_email_util(request, request.user, token)
    
    messages.success(request, 'A new verification email has been sent. Please check your inbox.')
    return redirect('sitevisitor:login') # Or a page confirming email resend

# --- Password Reset Views (Refactored to FBV) --- #
def custom_password_reset_view(request):
    template_name = 'sitevisitor/password_reset.html'
    email_template_name = 'sitevisitor/emails/password_reset_email.html'
    form_class = CustomPasswordResetForm
    success_url = reverse_lazy('sitevisitor:password_reset_done')
    
    if request.method == 'POST':
        form = form_class(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            User = get_user_model()
            # Check if a user with this email exists
            try:
                user = User.objects.get(email=email)
                # Only proceed if the user exists and is active
                if user.is_active:
                    # Add extra context with user information for the email template
                    extra_context = {
                        'user': user  # Pass the user object to the email template
                    }
                    
                    opts = {
                        'use_https': request.is_secure(),
                        'token_generator': default_token_generator,
                        'from_email': settings.DEFAULT_FROM_EMAIL,
                        'subject_template_name': 'sitevisitor/emails/password_reset_subject.txt',
                        'email_template_name': 'sitevisitor/emails/password_reset_email.html',
                        'html_email_template_name': email_template_name,
                        'request': request,
                        'extra_email_context': extra_context,  # Include the extra context
                        'domain_override': request.get_host(),
                    }
                    try:
                        form.save(**opts)
                        messages.success(request, f"A password reset link has been sent to {email}. Please check your inbox.")
                        return redirect(success_url)
                    except SMTPException as e:
                        # Handle SMTP errors
                        from django.urls import reverse
                        if 'authentication failed' in str(e).lower():
                            return redirect(reverse('sitevisitor:error_email') + '?type=invalid_api_key')
                        elif 'quota' in str(e).lower() or 'limit' in str(e).lower():
                            return redirect(reverse('sitevisitor:error_email') + '?type=quota_exceeded')
                        else:
                            return redirect(reverse('sitevisitor:error_email') + '?type=general')
                    except Exception as e:
                        messages.error(request, 'Unable to send password reset email. Please try again later.')
                        return render(request, template_name, {'form': form})
                else:
                    # For security reasons, we don't tell the user that the account is not active
                    messages.success(request, f"If an account with email {email} exists, a password reset link has been sent. Please check your inbox.")
                    return redirect(success_url)
            except User.DoesNotExist:
                # For security reasons, we don't tell the user that the account doesn't exist
                messages.success(request, f"If an account with email {email} exists, a password reset link has been sent. Please check your inbox.")
                return redirect(success_url)
        else:
            # If form is invalid, errors will be shown in the template
            pass
    else:
        form = form_class()
    
    context = {'form': form}
    return render(request, template_name, context)

def custom_password_reset_done_view(request):
    template_name = 'sitevisitor/password_reset_done.html'
    return render(request, template_name)

def custom_password_reset_confirm_view(request, uidb64=None, token=None):
    template_name = 'sitevisitor/password_reset_confirm.html'
    form_class = CustomSetPasswordForm
    success_url = reverse_lazy('sitevisitor:password_reset_complete')
    User = get_user_model()
    
    assert uidb64 is not None and token is not None  # Ensure parameters are present

    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is not None and default_token_generator.check_token(user, token):
        validlink = True
        if request.method == 'POST':
            form = form_class(user, request.POST)
            if form.is_valid():
                form.save()
                messages.success(request, 'Your password has been set. You may go ahead and log in now.')
                return redirect(success_url)
            else:
                messages.error(request, 'Please correct the error below.')
        else:
            form = form_class(user)
    else:
        validlink = False
        form = None
        messages.error(request, 'The password reset link was invalid, possibly because it has already been used. Please request a new password reset.')

    context = {'form': form, 'validlink': validlink}
    return render(request, template_name, context)

def custom_password_reset_complete_view(request):
    template_name = 'sitevisitor/password_reset_complete.html'
    return render(request, template_name)


# --- E-commerce Views --- #


def buy_view(request):
    """Handle adding a PRO plan to cart while preventing duplicate purchases."""
    product_id = request.GET.get('add-to-cart')
    from adminpanel.models import Subscription

    # Block duplicate purchases only
    if request.user.is_authenticated:
        profile, _ = Profile.objects.get_or_create(user=request.user)
        # Check if user has an ACTIVE subscription that is NOT expired
        if Subscription.objects.filter(
            user=request.user, 
            status='active', 
            end_date__gt=timezone.now()
        ).exists():
            messages.warning(request, "You already have an active PRO subscription. You can renew once it expires.")
            if 'cart' in request.session:
                del request.session['cart']
                request.session.modified = True
            return redirect('userpanel:dashboard')
        # Removed free trial blocking logic - users can now purchase PRO during free trial

    # Store the selected plan in the session cart
    if product_id:
        request.session['cart'] = {product_id: 1}
        request.session.modified = True

    # Force login before checkout
    if not request.user.is_authenticated:
        messages.info(request, "Please login to continue with your purchase.")
        return redirect(f"{reverse('sitevisitor:login')}?next={reverse('userpanel:cart')}")

    # Safe to proceed to cart
    return redirect('userpanel:cart')

def best_practices_view(request):
    """WhatsApp Campaign Best Practices - Avoid Bans & Scale Safely"""
    return render(request, 'sitevisitor/best_practices.html')

def robots_txt_view(request):
    from django.http import HttpResponse

    content = "\n".join([
        "# robots.txt for wacampaignsender.com",
        "# Allow all crawlers (search engines, AI bots, social preview bots)",
        "",
        "User-agent: *",
        "Disallow:",
        "",
        "# Sitemap",
        "Sitemap: https://wacampaignsender.com/sitemap.xml"
    ])
    return HttpResponse(content, content_type="text/plain")


def indexnow_key_view(request):
    """
    Returns IndexNow API key for verification
    """
    from django.http import HttpResponse
    return HttpResponse("2d26036c3e584873a854dfa997544388", content_type="text/plain")




def newsletter_subscribe(request):
    if request.method == 'POST':
        form = NewsletterForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            # Check if email already exists
            if NewsletterSubscriber.objects.filter(email=email).exists():
                messages.info(request, "You are already subscribed to our newsletter!")
            else:
                form.save()
                messages.success(request, "Thank you for subscribing to our newsletter!")
            return redirect('sitevisitor:home') # Redirect back to the homepage
        else:
            # If form is not valid, redirect to 400 error
            return redirect('sitevisitor:error_400')
    else:
        # Only POST allowed - redirect to 400 error
        return redirect('sitevisitor:error_400')

# Decorator for trial/subscription checks
def trial_or_subscription_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('sitevisitor:error_401')
        
        profile, _ = Profile.objects.get_or_create(user=request.user)
        from adminpanel.models import Subscription
        
        # Check if user has active subscription or trial
        has_subscription = Subscription.objects.filter(
            user=request.user, 
            status='active',
            end_date__gt=timezone.now()
        ).exists()
        
        if not has_subscription and not profile.on_free_trial:
            return redirect('sitevisitor:error_403')
        
        return view_func(request, *args, **kwargs)
    return _wrapped_view

# Rate limiting decorator
def rate_limit_check(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        # Simple rate limiting based on session
        session_key = f"rate_limit_{request.path}"
        last_request = request.session.get(session_key, 0)
        current_time = timezone.now().timestamp()
        
        if current_time - last_request < 1:  # 1 second rate limit
            return redirect('sitevisitor:error_429')
        
        request.session[session_key] = current_time
        return view_func(request, *args, **kwargs)
    return _wrapped_view


# --- Scenario-based Error Handling --- #

def handle_form_error(request, form, redirect_url='sitevisitor:home'):
    """Handle form validation errors"""
    if not form.is_valid():
        return redirect('sitevisitor:error_400')
    return None

def check_user_permissions(request, required_permission=None):
    """Check user permissions and redirect to appropriate error"""
    if not request.user.is_authenticated:
        return redirect('sitevisitor:error_401')
    
    if required_permission and not request.user.has_perm(required_permission):
        return redirect('sitevisitor:error_403')
    
    return None

# --- Social Auth Views --- #

def complete_social_signup(request):
    """Handle collecting full name from users who sign up with Google"""
    if not request.session.get('partial_pipeline_token'):
        messages.error(request, 'Invalid session. Please try signing up again.')
        return redirect('sitevisitor:signup')
    
    # Get the partial pipeline data
    from social_django.utils import load_strategy
    strategy = load_strategy(request)
    partial_token = request.session.get('partial_pipeline_token')
    
    try:
        partial_data = strategy.partial_load(partial_token)
        if not partial_data:
            messages.error(request, 'Session expired. Please try signing up again.')
            return redirect('sitevisitor:signup')
    except Exception as e:
        messages.error(request, 'Invalid session. Please try signing up again.')
        return redirect('sitevisitor:signup')
    
    # Get the user's name from the social auth data
    social_details = partial_data.kwargs.get('details', {})
    first_name = social_details.get('first_name', '')
    last_name = social_details.get('last_name', '')
    full_name = f"{first_name} {last_name}".strip()
    
    if request.method == 'POST':
        from .forms import SocialSignupForm
        form = SocialSignupForm(request.POST)
        if form.is_valid():
            full_name_form = form.cleaned_data['full_name']
            
            # Store the data in the session for the pipeline to use
            request.session['full_name'] = full_name_form
            
            # Continue with the pipeline - this will redirect to dashboard after completion
            return redirect(f"/social-auth/complete/google-oauth2/?token={partial_token}")
    else:
        from .forms import SocialSignupForm
        form = SocialSignupForm(initial={'full_name': full_name})
    
    return render(request, 'sitevisitor/complete_social_signup.html', {'form': form, 'full_name': full_name})

# --- Error Page Views --- #

def custom_400_view(request, exception=None):
    """Bad Request - 400"""
    return render(request, 'errors/400.html', {
        'error_code': '400',
        'error_title': 'Bad Request',
        'error_message': 'Oops! Something went wrong with your request.',
        'error_description': 'The URL or query parameters might be malformed.',
        'support_email': 'support@wacampaignsender.com'
    }, status=400)

def custom_401_view(request, exception=None):
    """Unauthorized - 401"""
    return render(request, 'errors/401.html', {
        'error_code': '401',
        'error_title': 'Session Expired',
        'error_message': 'Your session has expired or you need to upgrade your account.',
        'error_description': 'Please log in again or upgrade to access this feature.',
        'login_url': '/login/',
        'support_email': 'support@wacampaignsender.com'
    }, status=401)

def custom_403_view(request, exception=None):
    """Forbidden - 403"""
    return render(request, 'errors/403.html', {
        'error_code': '403',
        'error_title': 'Access Denied',
        'error_message': 'You don\'t have permission to view this resource.',
        'error_description': 'Contact your administrator or return to the homepage.',
        'pricing_url': '/userpanel/pricing/',
        'support_email': 'support@wacampaignsender.com'
    }, status=403)

def custom_404_view(request, exception=None):
    """Not Found - 404"""
    # Determine context based on URL path
    path = request.path
    if path.startswith('/userpanel/'):
        context_type = 'userpanel'
        back_url = '/userpanel/dashboard/'
        back_text = 'Back to Dashboard'
    elif path.startswith('/admin/'):
        context_type = 'adminpanel'
        back_url = '/admin/'
        back_text = 'Back to Admin'
    else:
        context_type = 'public'
        back_url = '/'
        back_text = 'Go to Homepage'
    
    return render(request, 'errors/404.html', {
        'error_code': '404',
        'error_title': 'Oops! Message Not Delivered',
        'error_message': 'The page you\'re looking for seems to have disappeared.',
        'error_description': 'You can head back to the homepage or try searching below.',
        'context_type': context_type,
        'back_url': back_url,
        'back_text': back_text,
        'support_email': 'support@wacampaignsender.com'
    }, status=404)

def custom_429_view(request, exception=None):
    """Too Many Requests - 429"""
    return render(request, 'errors/429.html', {
        'error_code': '429',
        'error_title': 'Slow Down There!',
        'error_message': 'You\'re sending requests too quickly.',
        'error_description': 'Please wait a moment before trying again to avoid being rate limited.',
        'retry_after': '60 seconds',
        'support_email': 'support@wacampaignsender.com'
    }, status=429)

def custom_500_view(request):
    """Internal Server Error - 500"""
    return render(request, 'errors/500.html', {
        'error_code': '500',
        'error_title': 'Server Error',
        'error_message': 'Something went wrong on our end.',
        'error_description': 'Our team has been automatically notified and is working to fix this issue.',
        'support_email': 'support@wacampaignsender.com'
    }, status=500)

def custom_503_view(request, exception=None):
    """Service Unavailable - 503"""
    return render(request, 'errors/503.html', {
        'error_code': '503',
        'error_title': 'Under Maintenance',
        'error_message': 'We\'re temporarily down for maintenance.',
        'error_description': 'We\'ll be back online shortly. Thank you for your patience.',
        'retry_after': '5 minutes',
        'support_email': 'support@wacampaignsender.com'
    }, status=503)

def custom_email_error_view(request, exception=None):
    """Email Service Error - Custom"""
    error_type = request.GET.get('type', 'general')
    
    if error_type == 'quota_exceeded':
        title = 'Email Quota Exceeded'
        message = 'We\'ve reached our daily email sending limit.'
        description = 'Please try again tomorrow or contact support for immediate assistance.'
    elif error_type == 'invalid_api_key':
        title = 'Email Configuration Error'
        message = 'There\'s an issue with our email service configuration.'
        description = 'Our team has been notified and is working to resolve this issue.'
    elif error_type == 'rate_limit':
        title = 'Email Rate Limit'
        message = 'Too many emails sent in a short period.'
        description = 'Please wait a few minutes before requesting another email.'
    elif error_type == 'blocked_sender':
        title = 'Email Delivery Issue'
        message = 'Unable to send email from this address.'
        description = 'Please contact support to resolve this delivery issue.'
    else:
        title = 'Email Service Error'
        message = 'Unable to send email at this time.'
        description = 'Please try again later or contact support if the issue persists.'
    
    return render(request, 'errors/email_error.html', {
        'error_code': 'EMAIL',
        'error_title': title,
        'error_message': message,
        'error_description': description,
        'error_type': error_type,
        'support_email': 'support@wacampaignsender.com'
    }, status=503)
