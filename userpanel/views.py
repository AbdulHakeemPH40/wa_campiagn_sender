from django.shortcuts import render, redirect, get_object_or_404
from paypal.standard.forms import PayPalPaymentsForm
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.contrib.auth import logout
from django.contrib import messages
from sitevisitor.models import WhatsAppNumber, FreeTrialPhone
from adminpanel.models import Subscription
from .forms import WhatsAppNumberForm
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.conf import settings
from django.urls import reverse
from django.db.models import Sum
# --- Added for new synchronous email sending ---
from userpanel.email_utils import send_payment_success_email
from .timezone_utils import convert_to_user_timezone, get_current_time_in_user_timezone
import uuid
import logging
logger = logging.getLogger(__name__)


import datetime
from .models import Order, OrderItem, Address
from sitevisitor.models import CustomUser, Profile
from .forms import UserProfileUpdateForm, UserPasswordChangeForm, AddressForm
from adminpanel.models import Subscription, Payment, SubscriptionPlan
from django.http import HttpResponse, JsonResponse, Http404, HttpResponseRedirect, HttpResponseForbidden
from django.views.decorators.http import require_POST
import json
from django.conf import settings
from django.contrib.auth import update_session_auth_hash, logout
from django.contrib.auth.decorators import login_required
from functools import wraps
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.urls import reverse
import json
import logging
from django.db.models import Sum

logger = logging.getLogger(__name__)


def paypal_return(request):
    """Handle PayPal return - both success and cancel (no login required for PayPal callbacks)"""
    try:
        # Get PayPal REST API parameters
        payment_id = request.GET.get('paymentId')  # PayPal REST API payment ID
        token = request.GET.get('token')  # PayPal token
        payer_id = request.GET.get('PayerID')  # Payer ID

        # Legacy parameters for NCP buttons
        tx = request.GET.get('tx')  # Transaction ID
        st = request.GET.get('st')  # Payment status

        logger.info(f"PayPal return: paymentId={payment_id}, token={token}, PayerID={payer_id}, tx={tx}, st={st}")

        # Check if payment was cancelled (no success parameters)
        if not payment_id and not token and not tx and not st:
            return paypal_cancel(request)

        # Find pending order - try multiple methods
        order = None
        pending_order_id = request.session.get('pending_order_id')
        url_user_id = request.GET.get('user_id')
        url_order_id = request.GET.get('order_id')
        
        # Method 1: If user is authenticated, use normal flow
        if request.user.is_authenticated:
            if pending_order_id:
                order = Order.objects.filter(
                    id=pending_order_id,
                    user=request.user,
                    status='pending'
                ).first()

            if not order:
                order = Order.objects.filter(
                    user=request.user,
                    status='pending'
                ).order_by('-created_at').first()
        
        # Method 2: Try URL parameters (user_id and order_id)
        if not order and url_user_id and url_order_id:
            try:
                from django.contrib.auth import get_user_model
                User = get_user_model()
                user = User.objects.get(id=int(url_user_id))
                order = Order.objects.filter(
                    id=int(url_order_id),
                    user=user,
                    status='pending'
                ).first()
                
                # Auto-login the user if found
                if order and not request.user.is_authenticated:
                    from django.contrib.auth import login
                    login(request, user, backend='django.contrib.auth.backends.ModelBackend')
                    logger.info(f"Auto-logged in user {user.email} via URL parameters")
            except (ValueError, User.DoesNotExist):
                pass
        
        # Method 3: Find by PayPal transaction details
        if not order:
            if payment_id:
                order = Order.objects.filter(
                    paypal_payment_id=payment_id,
                    status='pending'
                ).first()
            elif token:
                order = Order.objects.filter(
                    paypal_txn_id=token,
                    status='pending'
                ).first()
            elif tx:
                order = Order.objects.filter(
                    paypal_txn_id=tx,
                    status='pending'
                ).first()
            
            # If found order but no user session, log them in
            if order and order.user and not request.user.is_authenticated:
                from django.contrib.auth import login
                login(request, order.user, backend='django.contrib.auth.backends.ModelBackend')
                logger.info(f"Auto-logged in user {order.user.email} after PayPal return")

        if not order:
            if request.user.is_authenticated:
                messages.error(request, "No pending order found.")
                return redirect('userpanel:dashboard')
            else:
                # Redirect to login with error message
                messages.error(request, "Payment session expired. Please log in to continue.")
                return redirect('sitevisitor:login')

        # For NCP buttons - mark as completed and auto-activate immediately
        if tx or st == 'Completed':
            order.status = 'completed'  # Changed to completed immediately
            order.paypal_txn_id = tx or token or "ncp-{}".format(timezone.now().strftime('%Y%m%d%H%M%S'))
            # Reset order_id for proper numbering
            if order.order_id.startswith('P'):
                order.order_id = ''
            order.save()
            
            # Auto-process subscription immediately for NCP payments
            try:
                process_subscription_after_payment(order.user, order)
                logger.info("NCP payment completed and subscription activated: {}".format(tx or token))
                messages.success(request, "Payment successful! Your PRO subscription is now active.")
            except Exception as e:
                logger.error("Failed to process subscription for NCP payment: {}".format(e))
                messages.success(request, "Payment processed! Your subscription will be activated shortly.")
        
        # For REST API payments - execute first
        elif payment_id and payer_id:
            from .paypal_utils import PayPalAPI
            paypal_api = PayPalAPI()
            
            execution_result = paypal_api.execute_payment(payment_id, payer_id)
            
            if execution_result and execution_result.get('state') == 'approved':
                order.status = 'completed'  # Changed to completed immediately
                order.paypal_txn_id = payment_id
                # Reset order_id for proper numbering
                if order.order_id.startswith('P'):
                    order.order_id = ''
                order.save()
                
                # Auto-process subscription immediately for REST API payments
                try:
                    process_subscription_after_payment(order.user, order)
                    logger.info("REST API payment completed and subscription activated: {}".format(payment_id))
                    messages.success(request, "Payment successful! Your PRO subscription is now active.")
                except Exception as e:
                    logger.error("Failed to process subscription for REST API payment: {}".format(e))
                    messages.success(request, "Payment processed! Your subscription will be activated shortly.")
            else:
                logger.error(f"Payment execution failed: {execution_result}")
                messages.error(request, "Payment execution failed. Please try again.")
                return redirect('userpanel:cart')
        else:
            return paypal_cancel(request)

        # Clear session and cart
        if 'pending_order_id' in request.session:
            del request.session['pending_order_id']
        if 'cart' in request.session:
            del request.session['cart']
        request.session.modified = True

        return redirect('userpanel:dashboard')

    except Exception as e:
        logger.error(f"PayPal return error: {e}")
        messages.error(request, "Payment processing error. Please contact support.")
        if request.user.is_authenticated:
            return redirect('userpanel:dashboard')
        else:
            return redirect('sitevisitor:login')

def paypal_cancel(request):
    """Handle PayPal payment cancellation (no login required for PayPal callbacks)"""
    # Get pending order from session if available
    pending_order_id = request.session.get('pending_order_id')
    url_user_id = request.GET.get('user_id')
    url_order_id = request.GET.get('order_id')
    
    # Try to restore user session if not authenticated
    if not request.user.is_authenticated and url_user_id:
        try:
            from django.contrib.auth import get_user_model, login
            User = get_user_model()
            user = User.objects.get(id=int(url_user_id))
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            logger.info(f"Auto-logged in user {user.email} for payment cancellation")
        except (ValueError, User.DoesNotExist):
            pass

    if request.user.is_authenticated:
        # Cancel specific order if provided
        if url_order_id:
            try:
                Order.objects.filter(
                    id=int(url_order_id),
                    user=request.user,
                    status='pending'
                ).update(status='cancelled')
            except ValueError:
                pass
        elif pending_order_id:
            Order.objects.filter(
                id=pending_order_id,
                user=request.user,
                status='pending'
            ).update(status='cancelled')
            # Clear session
            del request.session['pending_order_id']
            request.session.modified = True
        else:
            # Fallback: cancel all pending orders
            Order.objects.filter(
                user=request.user,
                status='pending'
            ).update(status='cancelled')

        messages.warning(request, "Payment was cancelled. You can try again anytime.")
        return redirect('userpanel:cart')
    else:
        # User not authenticated - redirect to login
        messages.warning(request, "Payment was cancelled. Please log in to continue.")
        return redirect('sitevisitor:login')

def paypal_success_handler(request):
    """Handle PayPal SDK success callback (no login required for PayPal callbacks)"""
    return paypal_return(request)

def process_subscription_after_payment(user, order):
    """Process subscription creation after webhook confirmation"""
    try:
        from adminpanel.models import Subscription, SubscriptionPlan, Payment
        from django.utils import timezone

        # Determine plan based on order
        duration_days = 30
        plan_name = "WA PRO - 1 Month"

        first_item = order.items.first()
        if first_item:
            if "6 Month" in first_item.product_name:
                duration_days = 180
                plan_name = "WA PRO - 6 Month"
            elif "1 Year" in first_item.product_name:
                duration_days = 365
                plan_name = "WA PRO - 1 Year"

        # Get or create plan
        plan, _ = SubscriptionPlan.objects.get_or_create(
            name=plan_name,
            defaults={
                "description": f"{plan_name} plan",
                "price": order.total,
                "duration_days": duration_days,
                "is_active": True,
            }
        )

        # Create or update subscription
        end_date = timezone.now() + timezone.timedelta(days=duration_days)
        subscription, created = Subscription.objects.update_or_create(
            user=user,
            defaults={
                'plan': plan,
                'status': 'active',
                'end_date': end_date
            }
        )

        # Record payment (avoid duplicates)
        if not Payment.objects.filter(transaction_id=order.paypal_txn_id).exists():
            Payment.objects.create(
                user=user,
                subscription=subscription,
                amount=order.total,
                status='completed',
                transaction_id=order.paypal_txn_id,
                payment_method='PayPal'
            )

        # IMPORTANT: Deactivate free trial when PRO subscription is activated
        # This allows users to upgrade from trial to PRO immediately
        try:
            profile = user.profile
            if profile.on_free_trial:
                # Set trial end date to today to deactivate it
                profile.free_trial_end = timezone.now().date()
                profile.save()
                logger.info(f"Free trial deactivated for user {user.email} due to PRO subscription activation")
        except Exception as e:
            logger.error(f"Error deactivating free trial for user {user.email}: {e}")

        logger.info(f"Subscription processed for user {user.email}")

    except Exception as e:
        logger.error(f"Subscription processing error: {e}")


# Custom decorator to ensure only normal users can access these views
def normal_user_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('sitevisitor:home')

        if request.user.is_staff or request.user.is_superuser:
            messages.info(request, "Admin users are redirected to the admin panel.")
            return redirect(reverse('admin:index'))

        return view_func(request, *args, **kwargs)
    return _wrapped_view

@normal_user_required
def dashboard(request):
    """
    Renders the user dashboard page, displaying a list of the user's past orders.
    """
    # Check if we have been redirected from PayPal with completion params
    st = request.GET.get('st')
    if st == 'COMPLETED':
        tx = request.GET.get('tx') or request.GET.get('invoice')
        # Use existing handler to mark order and grant subscription
        return paypal_return(request)

    # Check if user just logged in via social auth and show welcome message
    if request.session.get('show_social_welcome'):
        from django.contrib import messages
        messages.success(request, f"Welcome {request.user.full_name}! Thanks for logging in.")
        # Clear the flag so message doesn't show again
        del request.session['show_social_welcome']

    orders = Order.objects.filter(user=request.user).order_by('-created_at')

    # Calculate total amount received from completed orders
    total_amount = Order.objects.filter(user=request.user, status='completed').aggregate(Sum('total'))['total__sum'] or 0

    context = {
        'orders': orders,
        'total_amount': total_amount,
    }
    return render(request, 'userpanel/dashboard.html', context)

@normal_user_required
def order_detail(request, order_id):
    """
    Displays the details of a specific order.
    """
    order = get_object_or_404(Order, id=order_id, user=request.user)
    context = {
        'order': order
    }
    return render(request, 'userpanel/order_detail.html', context)

@normal_user_required
def orders(request):
    """
    Renders the user orders page with their actual order history.
    """
    user_orders = Order.objects.filter(user=request.user).order_by('-created_at')
    context = {
        'orders': user_orders
    }
    return render(request, 'userpanel/orders.html', context)




@normal_user_required
def direct_paypal_redirect(request):
    """
    Creates an order for a single product and redirects to PayPal via a form.
    This is the secure way to handle direct payments, ensuring an order record
    exists and using the django-paypal form for redirection.
    """
    try:
        plan_type = request.GET.get('plan')

        if not plan_type:
            messages.error(request, "No plan selected.")
            return redirect('userpanel:pricing')

        # Get or create user profile
        profile, _ = Profile.objects.get_or_create(user=request.user)
        
        # Note: We now ALLOW PRO purchase during free trial
        # The trial will be deactivated when PRO subscription is activated

        # Check for existing active subscription (must be active status AND not expired)
        from adminpanel.models import Subscription
        if Subscription.objects.filter(
            user=request.user, 
            status='active', 
            end_date__gt=timezone.now()
        ).exists():
            messages.info(request, "You already have an active PRO subscription.")
            return redirect('userpanel:dashboard')

        # Product database with environment-specific PayPal buttons
        if settings.DEBUG:
            # Sandbox PayPal SDK buttons
            PRODUCTS_DB = {
                "PRO_MEMBERSHIP_1_MONTH": {
                    "name": "WA Campaign Sender PRO - 1 Month",
                    "price": 5.99,  # Limited Period Offer
                    "button_id": "7838N5GHUW2F2",
                },
                "PRO_MEMBERSHIP_6_MONTHS": {
                    "name": "WA Campaign Sender PRO - 6 Months",
                    "price": 29.95,  # Limited Period Offer
                    "button_id": "UMDQD6QR2WGDE",
                },
                "PRO_MEMBERSHIP_1_YEAR": {
                    "name": "WA Campaign Sender PRO - 1 Year",
                    "price": 59.00,  # Limited Period Offer
                    "button_id": "KV2K8MJBN98L6",
                },
            }
        else:
            # Production PayPal buttons
            PRODUCTS_DB = {
                "PRO_MEMBERSHIP_1_MONTH": {
                    "name": "WA Campaign Sender PRO - 1 Month",
                    "price": 5.99,  # Limited Period Offer
                    "paypal_link": "https://www.paypal.com/ncp/payment/E6NY74KQ94EG6",
                },
                "PRO_MEMBERSHIP_6_MONTHS": {
                    "name": "WA Campaign Sender PRO - 6 Months",
                    "price": 29.95,  # Limited Period Offer
                    "paypal_link": "https://www.paypal.com/ncp/payment/CRZZ9LTTHFCF2",
                },
                "PRO_MEMBERSHIP_1_YEAR": {
                    "name": "WA Campaign Sender PRO - 1 Year",
                    "price": 59.00,  # Limited Period Offer
                    "paypal_link": "https://www.paypal.com/ncp/payment/HTZ3KPTQQD5A4",
                },
            }

        if plan_type not in PRODUCTS_DB:
            messages.error(request, "Invalid subscription plan selected.")
            return redirect('userpanel:pricing')

        product_info = PRODUCTS_DB[plan_type]
        price = product_info['price']
        name = product_info['name']

        # Create the order with pending status.
        order = Order.objects.create(
            user=request.user,
            total=price,
            subtotal=price,
            status='pending',
            payment_method='PayPal',
            paypal_payment_id=''  # Will be set after PayPal payment creation
        )

        # Create a single order item for this direct purchase
        OrderItem.objects.create(
            order=order,
            product_name=name,
            product_description=f"Plan ID: {plan_type}",
            unit_price=price,
            quantity=1
        )

        # Get the host for constructing the URLs - handle both development and production
        if settings.DEBUG:
            protocol = 'http'
            host = '127.0.0.1:8000'
        else:
            protocol = 'https'
            host = request.get_host()

        # Build return URLs with user identification for session recovery
        return_url = f"{protocol}://{host}{reverse('userpanel:paypal_return')}?user_id={request.user.id}&order_id={order.id}"
        cancel_url = f"{protocol}://{host}{reverse('userpanel:paypal_cancel')}?user_id={request.user.id}&order_id={order.id}"

        # Use PayPal REST API for both development and production
        from .paypal_utils import PayPalAPI

        try:
            paypal_api = PayPalAPI()
            logger.info(f"Attempting PayPal payment creation for ${price}")

            payment_data = paypal_api.create_payment(
                amount=price,
                description=name
            )

            if payment_data and payment_data.get('id'):
                # Store PayPal payment ID in order
                order.paypal_payment_id = payment_data['id']
                # Also store in paypal_txn_id as fallback for finding orders
                if not order.paypal_txn_id:
                    order.paypal_txn_id = payment_data['id']
                order.save()

                # Store order ID in session for return handling
                request.session['pending_order_id'] = order.id
                request.session.modified = True

                # Find approval URL
                approval_url = None
                for link in payment_data.get('links', []):
                    if link.get('rel') == 'approval_url':
                        approval_url = link.get('href')
                        break

                if approval_url:
                    env = "Sandbox" if settings.DEBUG else "Live"
                    logger.info(f"PayPal API ({env}): Redirecting to {approval_url}")
                    return redirect(approval_url)
                else:
                    logger.error(f"PayPal approval URL not found in response: {payment_data}")
                    messages.error(request, "PayPal approval URL not found.")
                    return redirect('userpanel:cart')
            else:
                logger.error(f"PayPal payment creation failed. Response: {payment_data}")
                messages.error(request, "Failed to create PayPal payment. Please check your internet connection and try again.")
                return redirect('userpanel:cart')

        except Exception as api_error:
            logger.error(f"PayPal API Error: {api_error}", exc_info=True)
            messages.error(request, "PayPal service is temporarily unavailable. Please try again in a few minutes.")
            return redirect('userpanel:cart')

    except Exception as e:
        logger.error(f"Error in direct_paypal_redirect: {str(e)}", exc_info=True)
        if settings.DEBUG:
            messages.error(request, f"Debug Error: {str(e)}")
        else:
            messages.error(request, "An error occurred while processing your request. Please contact support if this persists.")
        return redirect('userpanel:cart')



def payment_success_view(request):
    """
    View for handling successful payments after PayPal redirect
    Automatically processes the payment when PayPal returns the user to this page
    """
    try:
        # Auto-login if user not authenticated but has valid order
        if not request.user.is_authenticated:
            url_user_id = request.GET.get('user_id')
            if url_user_id:
                try:
                    from django.contrib.auth import get_user_model, login
                    User = get_user_model()
                    user = User.objects.get(id=int(url_user_id))
                    login(request, user, backend='django.contrib.auth.backends.ModelBackend')
                except (ValueError, User.DoesNotExist):
                    pass
        
        if not request.user.is_authenticated:
            messages.error(request, "Please log in to continue.")
            return redirect('sitevisitor:login')
            
        # Check for existing pending order
        order = Order.objects.filter(
            user=request.user,
            status='pending'
        ).order_by('-created_at').first()

        # Development-only fallback removed – orders must be created *before* the user leaves for PayPal.
        # If no pending order exists at this point we simply show an error below.

        # Process the order if found or created
        if order:
            # Update the order status to completed (idempotent)
            if order.status != 'completed':
                order.status = 'completed'
            # Generate a transaction ID based on PayPal's token or current time
            txn_id = request.GET.get('token', None)
            if not txn_id:
                txn_id = f"dev-test-{timezone.now().strftime('%Y%m%d%H%M%S')}"

            order.paypal_txn_id = txn_id
            order.save()

            # --- Create or update Subscription for the user ---
            try:
                from adminpanel.models import Subscription
                from adminpanel.models import SubscriptionPlan
                duration_days = 30  # default duration
                first_item = order.items.first()
                if first_item:
                    name = getattr(first_item, 'product_name', '') or getattr(first_item, 'name', '')
                    # Determine plan and duration
                    plan_obj = None
                    if "6 Month" in name:
                        duration_days = 30 * 6
                        plan_obj, _ = SubscriptionPlan.objects.get_or_create(
                        name="WA PRO - 6 Month",
                        defaults={
                            "description": "6-Month WA Campaign Sender PRO plan",
                            "price": order.total,
                            "duration_days": duration_days,
                            "is_active": True,
                        },
                    )
                    elif "1 Year" in name:
                        duration_days = 365
                        plan_obj, _ = SubscriptionPlan.objects.get_or_create(
                        name="WA PRO - 1 Year",
                        defaults={
                            "description": "1-Year WA Campaign Sender PRO plan",
                            "price": order.total,
                            "duration_days": duration_days,
                            "is_active": True,
                        },
                    )
                    elif "1 Month" in name:
                        duration_days = 30
                        plan_obj, _ = SubscriptionPlan.objects.get_or_create(
                        name="WA PRO - 1 Month",
                        defaults={
                            "description": "1-Month WA Campaign Sender PRO plan",
                            "price": order.total,
                            "duration_days": duration_days,
                            "is_active": True,
                        },
                    )
                end_date = timezone.now() + timezone.timedelta(days=duration_days)

                existing_sub = Subscription.objects.filter(user=request.user, status='active').first()
                if existing_sub:
                    if not existing_sub.end_date or existing_sub.end_date < end_date:
                        if plan_obj and (not existing_sub.plan or existing_sub.plan != plan_obj):
                            existing_sub.plan = plan_obj
                        existing_sub.end_date = end_date
                        existing_sub.save(update_fields=['plan','end_date'])
                else:
                    Subscription.objects.create(
                        user=request.user,
                        status='active',
                        end_date=end_date,
                        plan=plan_obj
                    )
            except Exception as sub_err:
                logger.error(f'Failed to create/update subscription for order {order.order_id}: {sub_err}')

            # --- Record Payment ---
            try:
                if not Payment.objects.filter(transaction_id=txn_id).exists():
                    Payment.objects.create(
                        user=request.user,
                        subscription=Subscription.objects.filter(user=request.user, status='active').order_by('-end_date').first(),
                        amount=order.total,
                        status='completed',
                        transaction_id=txn_id,
                        payment_method='PayPal'
                    )
            except Exception as pay_err:
                logger.error(f'Failed to record payment for order {order.order_id}: {pay_err}')

            # Clear the cart
            if 'cart' in request.session:
                del request.session['cart']
                request.session.modified = True

            # Send invoice email to user
            try:
                # Send email using new synchronous utility (WeasyPrint-based)
                send_payment_success_email(order.id)
                logger.info(f"Payment success email (new util) sent for order {order.order_id}")
            except Exception as email_error:
                logger.error(f"Failed to send invoice email for order {order.order_id}: {str(email_error)}")

            messages.success(request, "Payment successful! Your subscription is now active. An invoice has been sent to your email.")
            return redirect('userpanel:dashboard')
        else:
            messages.warning(request, "Your cart is empty. Please select a plan before simulating payment.")
            return redirect('userpanel:pricing')
    except Exception as e:
        logger.error(f"Payment processing error: {str(e)}")
        # Show more detailed error message during development
        if settings.DEBUG:
            messages.error(request, f"Development Error: {str(e)}")
        else:
            messages.error(request, "An error occurred while processing your payment. Please contact support.")
        # Create the order anyway so at least there's progress
        try:
            if order and order.status == 'pending':
                order.status = 'completed'
                order.paypal_txn_id = f"forced-{timezone.now().strftime('%Y%m%d%H%M%S')}"
                order.save()
                if 'cart' in request.session:
                    del request.session['cart']
                    request.session.modified = True
                messages.success(request, "Despite the error, your order has been marked as completed.")
        except Exception as inner_e:
            logger.error(f"Forced order completion also failed: {str(inner_e)}")
        return redirect('userpanel:dashboard')

def _send_invoice_email(request, order):
    """
    Helper function to send invoice email to user after successful payment
    """
    from django.core.mail import EmailMessage
    from django.template.loader import render_to_string
    from django.utils.html import strip_tags
    import pdfkit
    from django.template.loader import get_template

    # Get order items
    order_items = order.items.all()

    # Calculate subscription period (start date and expiry date)
    start_date = order.created_at

    # Determine expiry date based on product name
    expiry_date = None
    subscription_period = None
    for item in order_items:
        if "1 Month" in item.product_name:
            expiry_date = start_date + timezone.timedelta(days=30)
            subscription_period = "1 Month"
            break
        elif "6 Months" in item.product_name:
            expiry_date = start_date + timezone.timedelta(days=30*6)
            subscription_period = "6 Months"
            break

    # Prepare context for email template
    context = {
        'order': order,
        'order_items': order_items,
        'company_name': 'WA Campaign Sender',
        'company_address': 'France Cluster, International City, Dubai,UAE',
        'company_support_email': 'hi@wacampaignsender.com',
        'subscription_start_date': start_date,
        'subscription_end_date': expiry_date,
        'subscription_period': subscription_period,
        'vat_note': 'VAT Not Applicable'
    }

    # Generate PDF invoice
    template = get_template('userpanel/order_invoice_pdf.html')
    html = template.render(context)

    # PDF options
    options = {
        'page-size': 'A4',
        'encoding': 'UTF-8',
        'no-outline': None
    }

    # Create PDF
    try:
        pdf = pdfkit.from_string(html, False, options=options)
    except Exception as e:
        logger.error(f"Error generating PDF for email: {e}")
        # Continue with email without PDF attachment if PDF generation fails
        pdf = None

    # Compose email
    subject = f"Your WA Campaign Sender Invoice #{order.order_id}"
    email_context = {
        'user': order.user,
        'order': order,
        'subscription_period': subscription_period,
        'start_date': start_date,
        'expiry_date': expiry_date,
        'support_email': 'hi@wacampaignsender.com'
    }

    html_message = render_to_string('emails/invoice_email.html', email_context)
    plain_message = strip_tags(html_message)

    # Send email
    email = EmailMessage(
        subject=subject,
        body=plain_message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[order.user.email]
    )
    email.content_subtype = "html"  # Main content is now HTML

    # Attach PDF if generated successfully
    if pdf:
        email.attach(f"Invoice-{order.order_id}.pdf", pdf, 'application/pdf')

    # Send email
    email.send(fail_silently=False)

def payment_failed_view(request):
    """
    View for handling failed or canceled payments from PayPal redirect
    Updates the order status to 'canceled' and provides options to retry
    """
    try:
        # Auto-login if user not authenticated but has valid order
        if not request.user.is_authenticated:
            url_user_id = request.GET.get('user_id')
            if url_user_id:
                try:
                    from django.contrib.auth import get_user_model, login
                    User = get_user_model()
                    user = User.objects.get(id=int(url_user_id))
                    login(request, user, backend='django.contrib.auth.backends.ModelBackend')
                except (ValueError, User.DoesNotExist):
                    pass
        
        if not request.user.is_authenticated:
            messages.warning(request, "Please log in to continue.")
            return redirect('sitevisitor:login')
            
        # Get the latest pending order for this user
        order = Order.objects.filter(
            user=request.user,
            status='pending'
        ).order_by('-created_at').first()

        if order:
            # Update the order status to canceled
            order.status = 'canceled'
            order.save()

            messages.warning(request, "Your payment was not completed or was canceled. You can try again from your cart.")
        else:
            messages.info(request, "No pending orders found.")

        # Redirect to cart so they can try again
        return redirect('userpanel:cart')
    except Exception as e:
        logger.error(f"Payment cancellation error: {str(e)}")
        messages.error(request, "An error occurred while processing your payment cancellation.")
        return redirect('userpanel:dashboard')



@normal_user_required
def view_order_invoice(request, order_id):
    # Check if this is an AJAX request
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.GET.get('is_ajax') == '1'

    try:
        # Get the order with all its items - ONLY COMPLETED ORDERS
        order = get_object_or_404(Order, order_id=order_id, user=request.user, status='completed')
        order_items = order.items.all()

        # Format for PDF or display
        format_pdf = request.GET.get('format') == 'pdf'

        # Calculate subscription period (start date and expiry date)
        start_date = order.created_at

        # Determine expiry date based on product name
        expiry_date = None
        subscription_period = None
        for item in order_items:
            if "1 Month" in item.product_name:
                expiry_date = start_date + timezone.timedelta(days=30)
                subscription_period = "1 Month"
                break
            elif "6 Months" in item.product_name:
                expiry_date = start_date + timezone.timedelta(days=30*6)
                subscription_period = "6 Months"
                break

        # Try to get the user's shipping address for the context, but don't fail if it's not there.
        user_address = None
        try:
            from .models import Address
            user_address = Address.objects.filter(user=request.user, is_default_shipping=True).first()
        except Exception as e:
            logger.warning(f"Could not fetch shipping address, which may be expected for digital products. Error: {e}")

        # Prepare context for template
        logo_data_uri = ''
        if format_pdf:
            import os, base64
            try:
                logo_path = os.path.join(settings.BASE_DIR, 'static', 'image', 'logo.png')
                if os.path.exists(logo_path):
                    with open(logo_path, 'rb') as logo_file:
                        logo_data_uri = 'data:image/png;base64,' + base64.b64encode(logo_file.read()).decode('utf-8')
            except Exception as logo_err:
                logger.warning(f"Could not embed logo in PDF for download: {logo_err}")
        context = {
            'logo_data_uri': logo_data_uri,
            'order': order,
            'order_items': order_items,
            'company_name': 'WA Campaign Sender',
            'company_address': 'France Cluster, International City, Dubai,UAE',
            'company_support_email': 'hi@wacampaignsender.com',
            'subscription_start_date': start_date,
            'subscription_end_date': expiry_date,
            'subscription_period': subscription_period,
            'vat_note': 'VAT Not Applicable',
            'user_address': user_address
        }

        if is_ajax:
            # Prepare items with description fallback
            items_data = []
            for item in order_items:
                item_data = {
                    'product_name': item.product_name,
                    'quantity': item.quantity,
                    'unit_price': float(item.unit_price),
                    'total_price': float(item.total_price),
                    'product_description': item.name  # Using item.name as description, as item.product doesn't exist
                }
                items_data.append(item_data)

            # Prepare user address data from the user_address object if it exists, otherwise use order details
            address_data = {}
            if user_address:
                address_data = {
                    'name': request.user.full_name,
                    'email': request.user.email,
                    'address_line1': user_address.address_line_1,
                    'address_line2': user_address.address_line_2 or '',
                    'city': user_address.city,
                    'state': user_address.state,
                    'country': user_address.country,
                    'postal_code': user_address.postal_code
                }
            else:
                # Fallback to order details if no default address is found
                address_data = {
                    'name': order.shipping_name or order.user.full_name,
                    'email': order.user.email,
                    'address_line1': order.shipping_address or 'Digital Product - No Shipping Address Required',
                    'address_line2': '',
                    'city': order.shipping_city or '',
                    'state': order.shipping_state or '',
                    'country': order.shipping_country or '',
                    'postal_code': order.shipping_postal_code or ''
                }

            # Prepare complete invoice data
            invoice_data = {
                'order_id': order.order_id,
                'date': order.created_at.strftime('%Y-%m-%d'),
                'total': f"${order.total:.2f}",
                'status': order.get_status_display(),
                'payment_method': "PayPal",
                'items': items_data,
                'subscription_period': subscription_period,
                'subscription_start': start_date.strftime('%Y-%m-%d'),
                'subscription_end': expiry_date.strftime('%Y-%m-%d') if expiry_date else None,
                'company_info': {
                    'name': 'WA Campaign Sender',
                    'address': 'France Cluster, International City, Dubai,UAE',
                    'support_email': 'hi@wacampaignsender.com'
                },
                'user_address': address_data
            }
            return JsonResponse(invoice_data)

        # If PDF is requested, generate PDF
        if format_pdf:
            try:
                from weasyprint import HTML
                from django.template.loader import render_to_string

                html_string = render_to_string('userpanel/order_invoice_pdf.html', context) # Changed to dedicated PDF template

                # IMPORTANT: Provide the base_url for WeasyPrint to resolve relative paths for images/CSS
                # If logo_url_for_pdf is used directly in template, base_url for images is less critical but good for CSS
                base_url = request.build_absolute_uri('/')

                # Generate PDF
                pdf_file = HTML(string=html_string, base_url=base_url).write_pdf()
                response = HttpResponse(pdf_file, content_type='application/pdf')
                response['Content-Disposition'] = f'attachment; filename="invoice-{order.order_id}.pdf"'
                return response
            except Exception as pdf_err:
                logger.error(f"Failed to generate PDF for order {order_id}. Error: {pdf_err}", exc_info=True)
                # Check for common WeasyPrint dependency errors
                if 'No such file or directory' in str(pdf_err) or 'cannot load library' in str(pdf_err) or 'failed to load' in str(pdf_err):
                    messages.error(request, "PDF generation failed. This is likely due to missing system dependencies (GTK3) required by the WeasyPrint library on Windows.")
                else:
                    messages.error(request, "An unexpected error occurred while creating the PDF file. Please check the server logs.")
                return redirect('userpanel:orders')

        # Otherwise render the HTML template
        return render(request, 'userpanel/order_invoice.html', context)

    except Order.DoesNotExist:
        if is_ajax:
            return JsonResponse({'error': 'Invoice not available - order not completed'}, status=404)
        messages.error(request, "Invoice not available. Only completed orders have invoices.")
        return redirect('userpanel:orders')
    except Exception as e:
        logger.error(f"Error fetching invoice data for order {order_id}: {e}")
        if is_ajax:
            return JsonResponse({'error': 'Could not retrieve invoice details'}, status=500)
        messages.error(request, "Could not retrieve invoice details.")
        return redirect('userpanel:orders')

@normal_user_required
def addresses(request):
    """
    Renders the user addresses page, displaying saved addresses.
    """
    user_addresses = Address.objects.filter(user=request.user)
    context = {
        'addresses': user_addresses,
    }
    return render(request, 'userpanel/addresses.html', context)

@normal_user_required
@require_POST
def add_address(request):
    """
    Handles adding a new address for the logged-in user using a form.
    """
    # Pass user to the form's __init__ method
    form = AddressForm(request.POST, user=request.user)
    if form.is_valid():
        form.save()
        messages.success(request, 'Address added successfully.')
    else:
        # Creating a flat string of errors to show in a single message
        error_list = [f'{field.replace("_", " ").title()}: {error}' for field, errors in form.errors.items() for error in errors]
        messages.error(request, f"Please correct the following errors: {'; '.join(error_list)}")
    return redirect('userpanel:addresses')

@normal_user_required
@require_POST
def edit_address(request, address_id):
    """
    Handles editing an existing address for the logged-in user.
    """
    address = get_object_or_404(Address, id=address_id, user=request.user)
    form = AddressForm(request.POST, instance=address)
    if form.is_valid():
        form.save()
        messages.success(request, 'Address updated successfully.')
    else:
        error_list = [f'{field.replace("_", " ").title()}: {error}' for field, errors in form.errors.items() for error in errors]
        messages.error(request, f"Please correct the following errors: {'; '.join(error_list)}")
    return redirect('userpanel:addresses')

@normal_user_required
def get_address_data(request, address_id):
    """
    Returns address data as JSON to populate the edit form.
    """
    address = get_object_or_404(Address, id=address_id, user=request.user)
    data = {
        'id': address.id,
        'address_line_1': address.address_line_1,
        'address_line_2': address.address_line_2,
        'city': address.city,
        'state': address.state,
        'postal_code': address.postal_code,
        'country': address.country,
        'is_default_shipping': address.is_default_shipping,
        'is_default_billing': address.is_default_billing,
    }
    return JsonResponse(data)


@normal_user_required
@require_POST
def delete_address(request, address_id):
    """
    Handles deleting an address for the logged-in user.
    """
    address = get_object_or_404(Address, id=address_id, user=request.user)
    try:
        address.delete()
        messages.success(request, 'Address deleted successfully.')
    except Exception as e:
        messages.error(request, f'There was an error deleting the address: {e}')
    return redirect('userpanel:addresses')


@normal_user_required
@require_POST
def set_default_address(request, address_id, address_type):
    """
    Sets a specific address as the default for shipping or billing.
    """
    address = get_object_or_404(Address, id=address_id, user=request.user)
    try:
        if address_type == 'shipping':
            address.is_default_shipping = True
            messages.success(request, 'Address set as default shipping.')
        elif address_type == 'billing':
            address.is_default_billing = True
            messages.success(request, 'Address set as default billing.')
        else:
            messages.error(request, 'Invalid address type specified.')
            return redirect('userpanel:addresses')

        address.save() # The model's save method handles unsetting other defaults
    except Exception as e:
        messages.error(request, f'There was an error setting the default address: {e}')
    return redirect('userpanel:addresses')

@normal_user_required
def settings_view(request):
    """
    Renders the user settings page, displaying profile information,
    subscription details, and WhatsApp number management.
    """
    # Get the user's profile. Create if it doesn't exist.
    profile, created = Profile.objects.get_or_create(user=request.user)

    # Fetch user profile and forms
    user_profile = request.user.profile
    profile_form = UserProfileUpdateForm(instance=request.user)
    whatsapp_number_form = WhatsAppNumberForm()

    # Handle form submissions
    if request.method == 'POST':
        if 'update_profile' in request.POST:
            profile_form = UserProfileUpdateForm(request.POST, request.FILES, instance=request.user)
            if profile_form.is_valid():
                profile_form.save()
                messages.success(request, 'Your profile has been updated successfully!')
                return redirect('userpanel:settings')
            else:
                messages.error(request, 'Please correct the errors below.')

        elif 'update_primary_whatsapp' in request.POST:
            new_primary_number = request.POST.get('primary_whatsapp_number', '').strip()
            primary_whatsapp_number_obj = WhatsAppNumber.objects.filter(profile__user=request.user, is_primary=True).first()

            if primary_whatsapp_number_obj:
                # Basic validation: check if number is not empty and is different
                if not new_primary_number:
                    messages.error(request, 'WhatsApp number cannot be empty.')
                elif new_primary_number == primary_whatsapp_number_obj.number:
                    messages.info(request, 'The primary WhatsApp number is already set to this value.')
                else:
                    # Check for uniqueness across all WhatsApp numbers (not just user's)
                    if WhatsAppNumber.objects.filter(number=new_primary_number).exists():
                        messages.error(request, 'This WhatsApp number is already in use by another account.')
                    else:
                        primary_whatsapp_number_obj.number = new_primary_number
                        primary_whatsapp_number_obj.save()
                        messages.success(request, 'Primary WhatsApp number updated successfully!')
                        return redirect('userpanel:settings')
            else:
                messages.error(request, 'No primary WhatsApp number found to update.')

    # Subscription details - ALWAYS show the latest subscription if it exists
    from django.utils import timezone
    from .timezone_utils import convert_to_user_timezone
    now = timezone.now()
    
    # First, try to get the most recent active subscription (including future end dates)
    subscription = Subscription.objects.filter(
        user=request.user,
        status='active'
    ).order_by('-created_at').first()
    
    # If no active subscription, get the most recent subscription regardless of status
    if not subscription:
        subscription = Subscription.objects.filter(user=request.user).order_by('-created_at').first()
    
    # Check if subscription is actually active (not expired)
    subscription_is_active = False
    if subscription:
        if subscription.status == 'active' and subscription.end_date and subscription.end_date > now:
            subscription_is_active = True
        elif subscription.status == 'active' and not subscription.end_date:
            # Admin granted subscription without end date
            subscription_is_active = True
        
    # Also check for processing orders (PayPal payment received but held)
    has_processing_order = Order.objects.filter(
        user=request.user,
        status__in=['processing', 'completed'],
        paypal_txn_id__isnull=False
    ).exists()

    # WhatsApp Number Management - Default to 1 for free users, more for PRO
    max_whatsapp_numbers = 1  # Default for free users
    if subscription and subscription_is_active:
        if subscription.plan:
            plan_name = subscription.plan.name.lower()
            if '1 month' in plan_name:
                max_whatsapp_numbers = 3
            elif '6 month' in plan_name or '6-month' in plan_name:
                max_whatsapp_numbers = 6
            elif '1 year' in plan_name or '12 month' in plan_name:
                max_whatsapp_numbers = 10
            # Fallback: use plan duration if name patterns fail
            elif subscription.plan and hasattr(subscription.plan, 'duration_days'):
                days = subscription.plan.duration_days or 0
                if days >= 365:
                    max_whatsapp_numbers = 10
                elif days >= 180:
                    max_whatsapp_numbers = 6
                elif days >= 30:
                    max_whatsapp_numbers = 3
        else:
            # Admin granted subscription without specific plan - allow 3 numbers
            max_whatsapp_numbers = 3

    current_whatsapp_numbers_count = WhatsAppNumber.objects.filter(profile__user=request.user).count()
    # Get the primary WhatsApp number
    primary_whatsapp_number = WhatsAppNumber.objects.filter(profile__user=request.user, is_primary=True).first()

    # Logging for debugging
    logger.info(f"Initial primary_whatsapp_number for user {request.user.username}: {primary_whatsapp_number}")

    if not primary_whatsapp_number:
        # If no primary number is found, try to designate an existing one as primary
        existing_whatsapp_number = WhatsAppNumber.objects.filter(profile__user=request.user).first()
        logger.info(f"Existing WhatsApp number found for user {request.user.username} (if any): {existing_whatsapp_number}")
        if existing_whatsapp_number:
            existing_whatsapp_number.is_primary = True
            existing_whatsapp_number.save()
            primary_whatsapp_number = existing_whatsapp_number # Update the variable for the current request
            logger.info(f"Designated {primary_whatsapp_number.number} as primary for user {request.user.username}")
        else:
            logger.info(f"No WhatsApp numbers found at all for user {request.user.username}.")

    # Determine if the primary WhatsApp number can be edited
    can_edit_primary_whatsapp = False
    if subscription and subscription_is_active: # Pro users with active subscription can always edit
        can_edit_primary_whatsapp = True
    elif not user_profile.free_trial_start: # Free trial users can edit if trial hasn't started
        can_edit_primary_whatsapp = True

    logger.info(f"Final primary_whatsapp_number for user {request.user.username}: {primary_whatsapp_number}")
    logger.info(f"can_edit_primary_whatsapp for user {request.user.username}: {can_edit_primary_whatsapp}")

    user_whatsapp_numbers = WhatsAppNumber.objects.filter(profile__user=request.user).exclude(is_primary=True)

    # Get current time in user's timezone from the browser cookie
    user_timezone = request.COOKIES.get('user_timezone', 'UTC')
    user_now = get_current_time_in_user_timezone(user_timezone)
    
    # Convert subscription end date to user's timezone if it exists
    if subscription and subscription.end_date:
        subscription.end_date = convert_to_user_timezone(subscription.end_date, user_timezone)
    
    context = {
        'profile_form': profile_form,
        'whatsapp_number_form': whatsapp_number_form,
        'subscription': subscription,
        'subscription_is_active': subscription_is_active,  # Add flag to indicate if subscription is truly active
        'has_processing_order': has_processing_order,
        'max_whatsapp_numbers': max_whatsapp_numbers,
        'current_whatsapp_numbers_count': current_whatsapp_numbers_count,
        'remaining_whatsapp_numbers': max(max_whatsapp_numbers - current_whatsapp_numbers_count, 0),
        'primary_whatsapp_number': primary_whatsapp_number,
        'user_whatsapp_numbers': user_whatsapp_numbers,
        'can_edit_primary_whatsapp': can_edit_primary_whatsapp,
        'user_profile': user_profile,  # Pass user_profile to context for free_trial_start check in template if needed
        'user_profile_picture_url': user_profile.profile_picture.url if getattr(user_profile, 'profile_picture', None) else '',
        'now': user_now,  # Add current time in user's timezone for subscription status comparison
        'user_timezone': user_timezone,  # Pass user's timezone to template
    }

    return render(request, 'userpanel/settings.html', context)


@normal_user_required
def change_password_view(request):
    """
    Renders the dedicated password change page and handles password updates.
    Redirects back to settings page after successful password change.
    """
    if request.method == 'POST':
        form = UserPasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)  # Keep user logged in after password change
            messages.success(request, 'Your password has been successfully updated!')
            return redirect('userpanel:settings')
    else:
        form = UserPasswordChangeForm(request.user)
    
    return render(request, 'userpanel/change_password.html', {
        'form': form,
    })


@normal_user_required
def add_whatsapp_number(request):
    from .forms import WhatsAppNumberForm
    from sitevisitor.models import WhatsAppNumber

    if request.method == 'POST':
        form = WhatsAppNumberForm(request.POST)
        if form.is_valid():
            whatsapp_number = form.cleaned_data['whatsapp_number']

            # Ensure user has a profile (important for admin-created users)
            profile, created = Profile.objects.get_or_create(user=request.user)

            # Normalize the number
            normalized_number = whatsapp_number.lstrip('+')

            # Check if the number already exists for this user
            if WhatsAppNumber.objects.filter(profile__user=request.user, number=normalized_number).exists():
                messages.error(request, 'This WhatsApp number is already added to your account.')
                return redirect('userpanel:settings')

            # Check if the number exists for any other user (uniqueness across all users)
            if WhatsAppNumber.objects.filter(number=normalized_number).exclude(profile__user=request.user).exists():
                messages.error(request, 'This WhatsApp number is already in use by another account.')
                return redirect('userpanel:settings')

            # Check license limits - include admin granted subscriptions
            from django.utils import timezone
            subscription = Subscription.objects.filter(
                user=request.user,
                status='active',
                end_date__gt=timezone.now()
            ).first()

            # If no active subscription, check for any subscription
            if not subscription:
                subscription = Subscription.objects.filter(user=request.user).order_by('-created_at').first()
            max_whatsapp_numbers = 1  # Default for free users
            if subscription:
                if subscription.plan:
                    plan_name = subscription.plan.name.lower()
                    if '1 month' in plan_name:
                        max_whatsapp_numbers = 3
                    elif '6 month' in plan_name or '6-month' in plan_name:
                        max_whatsapp_numbers = 6
                    elif '1 year' in plan_name or '12 month' in plan_name:
                        max_whatsapp_numbers = 10
                    # Fallback based on plan duration
                    elif hasattr(subscription.plan, 'duration_days'):
                        days = subscription.plan.duration_days or 0
                        if days >= 365:
                            max_whatsapp_numbers = 10
                        elif days >= 180:
                            max_whatsapp_numbers = 6
                        elif days >= 30:
                            max_whatsapp_numbers = 3
                else:
                    # Admin granted subscription without specific plan - allow 3 numbers
                    max_whatsapp_numbers = 3

            current_whatsapp_numbers_count = WhatsAppNumber.objects.filter(profile__user=request.user).count()

            if current_whatsapp_numbers_count >= 10:
                messages.error(request, f'Maximum 10 WhatsApp numbers allowed. You have reached the limit.')
                return redirect('userpanel:settings')
            elif current_whatsapp_numbers_count >= max_whatsapp_numbers:
                messages.error(request, f'You have reached your limit of {max_whatsapp_numbers} WhatsApp numbers based on your subscription plan. Please upgrade your plan or remove an existing number.')
                return redirect('userpanel:settings')

            # Determine if this should be the primary number
            is_primary = not WhatsAppNumber.objects.filter(profile__user=request.user, is_primary=True).exists()

            # Normalize number (remove + prefix)
            normalized_number = whatsapp_number.lstrip('+')

            # Create WhatsApp number
            wa_number = WhatsAppNumber.objects.create(
                profile=profile,
                number=normalized_number,
                is_primary=is_primary,
                is_active=True  # Activate subscription when number is added
            )

            # Auto-activate subscription based on number count
            try:
                from adminpanel.models import SubscriptionPlan
                total_numbers = WhatsAppNumber.objects.filter(profile__user=request.user).count()

                # Determine plan based on number count
                if total_numbers <= 3:
                    plan_name = "WA PRO - 1 Month"
                    duration_days = 30
                elif total_numbers <= 6:
                    plan_name = "WA PRO - 6 Month"
                    duration_days = 180
                elif total_numbers <= 10:
                    plan_name = "WA PRO - 1 Year"
                    duration_days = 365
                else:
                    messages.error(request, f'Maximum 10 WhatsApp numbers allowed.')
                    return redirect('userpanel:settings')

                # Get or create plan
                plan, _ = SubscriptionPlan.objects.get_or_create(
                    name=plan_name,
                    defaults={
                        "description": f"{plan_name} plan",
                        "price": 5.99 if duration_days == 30 else (29.95 if duration_days == 180 else 59.00),  # Limited Period Offer
                        "duration_days": duration_days,
                        "is_active": True,
                    }
                )

                # Create or update subscription
                subscription, created = Subscription.objects.get_or_create(
                    user=request.user,
                    defaults={
                        'plan': plan,
                        'status': 'active',
                        'end_date': timezone.now() + datetime.timedelta(days=duration_days)
                    }
                )

                if not created:
                    subscription.plan = plan
                    subscription.status = 'active'
                    subscription.end_date = timezone.now() + datetime.timedelta(days=duration_days)
                    subscription.save()

                if is_primary:
                    messages.success(request, f'WhatsApp number added as primary! {plan_name} activated.')
                else:
                    messages.success(request, f'WhatsApp number added! {plan_name} activated.')

            except Exception as e:
                logger.error(f'Auto-subscription activation failed: {e}')
                if is_primary:
                    messages.success(request, 'WhatsApp number added as primary!')
                else:
                    messages.success(request, 'WhatsApp number added successfully!')
            return redirect('userpanel:settings')
    else:
        form = WhatsAppNumberForm()

    return redirect('userpanel:settings')

@normal_user_required
def remove_whatsapp_number(request, whatsapp_number_id):
    whatsapp_number_obj = get_object_or_404(WhatsAppNumber, id=whatsapp_number_id, profile__user=request.user)
    whatsapp_number_obj.delete()
    messages.success(request, 'WhatsApp number removed successfully!')
    return redirect('userpanel:settings')

    return redirect('userpanel:settings')

@login_required
def pricing_view(request):
    """
    Displays the pricing page for logged-in users.
    Redirect PRO users away to dashboard.
    """
    from adminpanel.models import Subscription
    # Check if user has an ACTIVE subscription that is NOT expired
    if Subscription.objects.filter(
        user=request.user, 
        status='active', 
        end_date__gt=timezone.now()
    ).exists():
        messages.info(request, "You already have an active PRO subscription. No need to purchase again.")
        return redirect('userpanel:dashboard')
    return render(request, 'userpanel/pricing.html')

@login_required
def clear_cart_view(request):
    if request.method == 'POST':
        if 'cart' in request.session:
            del request.session['cart']
            request.session.modified = True
            return JsonResponse({'status': 'success', 'message': 'Cart cleared.'})
        return JsonResponse({'status': 'success', 'message': 'Cart was already empty.'})
    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)



@login_required
def add_to_cart_view(request):
    product_id = request.GET.get('add-to-cart')
    if product_id:
        profile, _ = Profile.objects.get_or_create(user=request.user)

        from adminpanel.models import Subscription
        # Check if user has an ACTIVE subscription that is NOT expired
        if Subscription.objects.filter(
            user=request.user, 
            status='active', 
            end_date__gt=timezone.now()
        ).exists():
            messages.warning(request, "You already have an active PRO subscription. You cannot purchase another one.")
            return redirect('userpanel:dashboard')

        # Note: We now ALLOW PRO purchase during free trial
        # The trial will be deactivated when PRO subscription is activated

        # Clear any previous items and add the selected plan
        cart = {product_id: 1}
        request.session['cart'] = cart
        request.session.modified = True

        # Create pending order for PayPal SDK integration
        PRODUCTS_DB = {
            "PRO_MEMBERSHIP_1_MONTH": {"name": "WA Campaign Sender PRO - 1 Month", "price": 5.99},  # Limited Period Offer
            "PRO_MEMBERSHIP_6_MONTHS": {"name": "WA Campaign Sender PRO - 6 Months", "price": 29.95},  # Limited Period Offer
            "PRO_MEMBERSHIP_1_YEAR": {"name": "WA Campaign Sender PRO - 1 Year", "price": 59.00},  # Limited Period Offer
        }

        if product_id in PRODUCTS_DB:
            product_info = PRODUCTS_DB[product_id]
            order = Order.objects.create(
                user=request.user,
                total=product_info['price'],
                subtotal=product_info['price'],
                status='pending',
                payment_method='PayPal'
            )

            OrderItem.objects.create(
                order=order,
                product_name=product_info['name'],
                product_description=f"Plan ID: {product_id}",
                unit_price=product_info['price'],
                quantity=1
            )

            request.session['pending_order_id'] = order.id
            request.session.modified = True

        messages.success(request, "The selected plan has been placed in your cart.")
    return redirect('userpanel:cart')

@login_required
def cart_view(request):
    cart_data = request.session.get('cart', {})

    from adminpanel.models import Subscription
    if Subscription.objects.filter(user=request.user, status='active').exists():
        messages.info(request, "You already have an active PRO subscription. No need to purchase again.")
        if 'cart' in request.session:
            del request.session['cart']
            request.session.modified = True
        return redirect('userpanel:dashboard')

    if not cart_data:
        messages.info(request, "Your cart is empty. Let's find a plan for you!")
        return redirect('userpanel:pricing')

    # Check if the user already has an active subscription
    user_profile = None
    try:
        user_profile = request.user.profile
    except Profile.DoesNotExist:
        pass # Profile will be created if needed later

    from adminpanel.models import Subscription
    # Check if user has an ACTIVE subscription that is NOT expired
    # This ensures cancelled subscriptions don't block repurchase
    is_pro_user = Subscription.objects.filter(
        user=request.user,
        status='active',
        end_date__gt=timezone.now()  # Must be active AND not expired
    ).exists()

    # Redirect PRO users away from cart if they attempt duplicate purchase
    if is_pro_user:
        messages.info(request, "You already have an active PRO subscription. No need to purchase again.")
        if 'cart' in request.session:
            del request.session['cart']
            request.session.modified = True
        return redirect('userpanel:dashboard')

    # If user is already pro and trying to buy a pro membership, redirect or show message
    if is_pro_user:
        contains_pro_item = False
        for product_id in cart_data.keys():
            if "PRO_MEMBERSHIP" in product_id:
                contains_pro_item = True
                break

        if contains_pro_item: # If they are pro and cart has pro items, redirect with warning
            messages.warning(request, "You already have an active PRO membership. You cannot purchase another one.")
            return redirect('userpanel:dashboard')
        else: # If they are pro and cart has no pro items, redirect with info
            messages.info(request, "You already have an active PRO membership. No further purchase is needed.")
            return redirect('userpanel:dashboard')


    # Environment-specific PayPal configuration
    if settings.DEBUG:
        # Development: Use sandbox buttons
        PRODUCTS_DB = {
            "PRO_MEMBERSHIP_1_MONTH": {
                "name": "WA Campaign Sender PRO - 1 Month",
                "price": 5.99,  # Limited Period Offer
                "button_id": "7838N5GHUW2F2",
                "description": "Start your WhatsApp marketing journey with 1 month of access to WA Campaign Sender PRO.",
                "features": [
                    "Bulk messaging",
                    "Contact extractor",
                    "Pause/Resume support",
                    "Anti-ban logic",
                    "Real-time message delivery reports"
                ],
                "note": "Great for short-term campaigns or trials. Supports up to 3 WhatsApp numbers."
            },
            "PRO_MEMBERSHIP_6_MONTHS": {
                "name": "WA Campaign Sender PRO - 6 Months",
                "price": 29.95,  # Limited Period Offer
                "button_id": "UMDQD6QR2WGDE",
                "description": "Perfect for growing businesses with 6 months of PRO access.",
                "features": [
                    "All 1-month features",
                    "Priority support",
                    "Advanced analytics",
                    "Campaign scheduling"
                ],
                "note": "Best value for medium-term campaigns. Supports up to 6 WhatsApp numbers."
            },
            "PRO_MEMBERSHIP_1_YEAR": {
                "name": "WA Campaign Sender PRO - 1 Year",
                "price": 59.00,  # Limited Period Offer
                "button_id": "KV2K8MJBN98L6",
                "description": "Complete WhatsApp marketing solution for serious businesses.",
                "features": [
                    "All premium features",
                    "Dedicated support",
                    "Custom integrations",
                    "Advanced reporting"
                ],
                "note": "Maximum value for long-term success. Supports up to 10 WhatsApp numbers."
            },
        }
    else:
        # Production: Use NCP buttons
        PRODUCTS_DB = {
            "PRO_MEMBERSHIP_1_MONTH": {
                "name": "WA Campaign Sender PRO - 1 Month",
                "price": 5.99,  
                "paypal_link": "https://www.paypal.com/ncp/payment/E6NY74KQ94EG6"
            },
            "PRO_MEMBERSHIP_6_MONTHS": {
                "name": "WA Campaign Sender PRO - 6 Months",
                "price": 29.95,
                "paypal_link": "https://www.paypal.com/ncp/payment/CRZZ9LTTHFCF2"
            },
            "PRO_MEMBERSHIP_1_YEAR": {
                "name": "WA Campaign Sender PRO - 1 Year",
                "price": 59.00,
                "paypal_link": "https://www.paypal.com/ncp/payment/HTZ3KPTQQD5A4"
            },
        }

    processed_cart_items = []
    cart_subtotal = 0

    for product_id, quantity in cart_data.items():
        product_info = PRODUCTS_DB.get(product_id, {"name": f"Product ID: {product_id}", "price": 0.00})
        item_total_price = product_info['price'] * quantity

        # Build link to internal PayPal redirect view so we always create an Order before leaving our site
        pay_link = reverse('userpanel:direct_paypal_redirect') + f'?plan={product_id}'

        processed_cart_items.append({
            'id': product_id,
            'name': product_info['name'],
            'quantity': quantity,
            'price_per_unit': product_info['price'],
            'item_total_price': item_total_price,
            'paypal_link': pay_link,
        })
        cart_subtotal += item_total_price

    cart_total_overall = cart_subtotal

    default_shipping_address = None
    # user_profile is already determined above


    try:
        default_shipping_address = Address.objects.get(user=request.user, is_default_shipping=True)
    except Address.DoesNotExist:
        pass

    saved_payment_methods = []

    # Flag indicating whether the user is currently on an active free trial (not cancelled)
    # NOTE: This is for informational purposes only - users CAN purchase PRO during free trial
    on_free_trial = False
    if user_profile:
        # Check if free trial is active but NOT cancelled by admin
        on_free_trial = user_profile.on_free_trial and not user_profile.free_trial_cancelled

    context = {
        'cart_items': processed_cart_items,
        'cart_subtotal': cart_subtotal,
        'cart_total_overall': cart_total_overall,
        'user_profile': user_profile,
        'default_shipping_address': default_shipping_address,
        'on_free_trial': on_free_trial,
        'is_pro_user': is_pro_user,
        'debug': settings.DEBUG,
    }
    return render(request, 'userpanel/cart.html', context)



def logout_view(request):
    """
    Logs the user out and redirects to the site visitor homepage.
    """
    logout(request)
    return redirect('sitevisitor:home')

# ---------------- Free Trial -----------------

# ---------------- Development Simulation Views (Commented out for deployment) -----------------


@login_required
def free_trial_confirmation(request):
    """Show confirmation dialog before free trial activation"""
    if not request.user.is_authenticated:
        messages.error(request, "Please log in to activate free trial.")
        return redirect('sitevisitor:login')
    
    profile, _ = Profile.objects.get_or_create(user=request.user)
    
    from adminpanel.models import Subscription
    # Check if user has active subscription
    if Subscription.objects.filter(user=request.user, status='active').exists():
        messages.error(request, "You already have an active PRO subscription; free trial is not available.")
        return redirect('userpanel:settings')
    
    # Check if user has previously purchased PRO
    if Subscription.objects.filter(user=request.user).exists():
        messages.error(request, "Free trial is not available for users who have previously purchased PRO subscriptions.")
        return redirect('userpanel:pricing')
    
    # Check if free trial already used
    if profile.free_trial_used:
        messages.error(request, "You have already used your free trial.")
        return redirect('userpanel:pricing')
    
    # Get user's primary WhatsApp number
    primary_whatsapp_number = WhatsAppNumber.objects.filter(profile=profile, is_primary=True).first()
    phone_number = primary_whatsapp_number.number if primary_whatsapp_number else request.user.phone_number
    
    if not phone_number:
        messages.error(request, "A WhatsApp number is required to activate the free trial. Please add one in your profile settings.")
        return redirect('userpanel:settings')
    
    # Check if phone number already used for free trial
    from sitevisitor.models import FreeTrialPhone
    if FreeTrialPhone.objects.filter(phone=phone_number).exists():
        messages.error(request, "This WhatsApp number has already been used for a free trial.")
        return redirect('userpanel:pricing')
    
    # Format phone number with country code for display
    formatted_number = phone_number
    if not phone_number.startswith('+'):
        # Add + if not present
        formatted_number = f"+{phone_number}"
    
    context = {
        'whatsapp_number': formatted_number,
        'user': request.user,
    }
    
    return render(request, 'userpanel/free_trial_confirmation.html', context)

def start_free_trial(request):
    if request.method == 'POST':
        # Check if confirmation was provided
        if not request.POST.get('confirmed'):
            # Redirect to confirmation page if not confirmed
            return redirect('userpanel:free_trial_confirmation')
        
        profile, _ = Profile.objects.get_or_create(user=request.user)

        from adminpanel.models import Subscription
        # Check if user has active subscription
        if Subscription.objects.filter(user=request.user, status='active').exists():
            messages.error(request, "You already have an active PRO subscription; free trial is not available.")
            return redirect('userpanel:settings')
        
        # IMPORTANT: Prevent users who have EVER purchased PRO from activating free trial
        # This prevents abuse where users buy PRO, then try to get free trial later
        if Subscription.objects.filter(user=request.user).exists():
            messages.error(request, "Free trial is not available for users who have previously purchased PRO subscriptions.")
            return redirect('userpanel:pricing')

        # Prevent misuse by checking phone number history
        from sitevisitor.models import FreeTrialPhone
        # Get the primary WhatsApp number for the user's profile, or fallback to user's phone_number
        primary_whatsapp_number = WhatsAppNumber.objects.filter(profile=profile, is_primary=True).first()
        phone_number = primary_whatsapp_number.number if primary_whatsapp_number else request.user.phone_number
        if phone_number and FreeTrialPhone.objects.filter(phone=phone_number).exists():
            messages.error(request, "This mobile number has already been used for a free trial.")
            return redirect('userpanel:pricing')

        if profile.free_trial_used:
            messages.error(request, "You have already used your free trial.")
            return redirect('userpanel:pricing')

        # --- NEW: Prevent misuse by checking phone number history ---
        # Get the primary WhatsApp number for the user's profile, or fallback to user's phone_number
        primary_whatsapp_number = WhatsAppNumber.objects.filter(profile=profile, is_primary=True).first()
        phone_number = primary_whatsapp_number.number if primary_whatsapp_number else request.user.phone_number

        if phone_number:
            if FreeTrialPhone.objects.filter(phone=phone_number).exists():
                messages.error(request, "This mobile number has already been used for a free trial.")
                return redirect('userpanel:pricing')
        else:
            # If no phone number is associated, perhaps prompt the user to add one or disallow free trial
            messages.error(request, "A phone number is required to activate the free trial. Please add one in your profile settings.")
            return redirect('userpanel:settings')

        # Use get_user_local_date() to respect user's timezone
        from userpanel.timezone_utils import get_user_local_date
        today = get_user_local_date()
        profile.free_trial_start = today
        profile.free_trial_end = today + datetime.timedelta(days=14)
        profile.save(update_fields=['free_trial_start', 'free_trial_end'])

        # Record the phone number as having used a free trial
        if phone_number: # Only record if a phone number was found
            FreeTrialPhone.objects.create(phone=phone_number, user=request.user)

        # NEW: Send free trial activation HTML email
        subject = "Your Free Trial Has Been Activated!"
        from_email = settings.DEFAULT_FROM_EMAIL
        recipient_list = [request.user.email]

        # Context for the email template
        # Calculate trial duration and days remaining
        trial_days = 14  # Default free trial duration
        days_remaining = (profile.free_trial_end - timezone.now().date()).days if profile.free_trial_end else 0
        
        email_context = {
            'user': request.user,
            'trial_days': trial_days,
            'start_date': profile.free_trial_start or timezone.now().date(),
            'end_date': profile.free_trial_end,
            'days_remaining': max(0, days_remaining),  # Ensure non-negative
            'domain': 'www.wacampaignsender.com',
            'now': timezone.now()
        }

        # Render HTML and plain text versions
        html_content = render_to_string('userpanel/email/free_trial_activated.html', email_context)
        text_content = (
            f"Dear {request.user.full_name},\\n\\n"
            "Congratulations! Your 14-day free trial for WA Campaign Sender has been successfully activated.\\n\\n"
            f"Your trial period will end on {profile.free_trial_end.strftime('%Y-%m-%d')}.\\n\\n"
            "During this period, you'll have full access to all our premium features. "
            "Start exploring and supercharge your campaigns!\\n\\n"
            f"Go to Dashboard: https://www.wacampaignsender.com/userpanel/\\n\\n"
            "If you have any questions, feel free to contact our support team.\\n\\n"
            "Best regards,\\n"
            "The WA Campaign Sender Team"
        )

        try:
            msg = EmailMultiAlternatives(subject, text_content, from_email, recipient_list)
            msg.attach_alternative(html_content, "text/html")
            msg.send(fail_silently=False)
            messages.success(request, "Free trial activated! An email with trial details has been sent to you.")
        except Exception as e:
            messages.warning(request, f"Free trial activated, but failed to send activation email. Error: {e}")
            logger.error(f"Failed to send free trial activation email to {request.user.email}: {e}")

        return redirect('userpanel:settings')
    else:
        return redirect('userpanel:pricing')
