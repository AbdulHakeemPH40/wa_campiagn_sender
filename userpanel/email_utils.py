from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse # For building absolute URIs if needed in email
from django.utils import timezone
from django.utils.html import strip_tags

from .models import Order # Assuming Order model is in userpanel.models
# Lazy import for WeasyPrint to avoid GTK dependency errors on Windows during startup
import logging
import os, base64

logger = logging.getLogger(__name__)

# Helper function to generate PDF (adapted from view_order_invoice)
def generate_invoice_pdf_for_email(order):
    # Skip PDF generation in DEBUG mode (WeasyPrint requires GTK on Windows)
    if settings.DEBUG:
        logger.info(f"DEBUG mode: Skipping PDF generation for order {order.id} (WeasyPrint requires GTK)")
        return None
    
    try:
        start_date = order.created_at
        expiry_date = None
        subscription_period = None
        for item in order.items.all():
            product_name = item.product_name.lower()
            if "6 month" in product_name:
                expiry_date = start_date + timezone.timedelta(days=30*6)
                subscription_period = "6 Months"
                break
            elif "1 month" in product_name or "base" in product_name or "api" in product_name:
                expiry_date = start_date + timezone.timedelta(days=30)
                subscription_period = "1 Month"
                break
        
        # Default to 1 month if no match found
        if not subscription_period:
            expiry_date = start_date + timezone.timedelta(days=30)
            subscription_period = "1 Month"

        # Embed logo image as base64 data URI so WeasyPrint can render it without external file access
        logo_data_uri = ''
        try:
            logo_path = os.path.join(settings.BASE_DIR, 'static', 'image', 'Logo.png')
            if os.path.exists(logo_path):
                with open(logo_path, 'rb') as logo_file:
                    logo_data_uri = 'data:image/png;base64,' + base64.b64encode(logo_file.read()).decode('utf-8')
        except Exception as logo_exc:
            logger.warning(f'Could not embed logo in PDF: {logo_exc}')

        context = {
            'order': order,
            'order_items': order.items.all(),
            'company_name': 'Focus Web Solutions',
            'company_address': 'Grand Hamad Bank Street, Doha - Qatar',
            'company_support_email': 'hi@wacampaignsender.com',
            'subscription_start_date': start_date,
            'subscription_end_date': expiry_date,
            'subscription_period': subscription_period,
            'vat_note': 'VAT Not Applicable',
            'logo_data_uri': logo_data_uri,
            # If SITE_URL is defined and your PDF template needs absolute URLs for static assets:
            # 'site_url': getattr(settings, 'SITE_URL', ''), 
        }
        html_string = render_to_string('userpanel/order_invoice_pdf.html', context)
        
        # base_url can be tricky for WeasyPrint. If your static files (like logos)
        # are not rendering correctly in the PDF, you might need to pass an explicit
        # base_url=settings.SITE_URL or ensure your PDF template uses full URLs for assets.
        # Lazy import WeasyPrint only when needed to avoid Windows GTK errors
        from weasyprint import HTML
        pdf_file = HTML(string=html_string).write_pdf()
        return pdf_file
    except Exception as e:
        logger.error(f"Error generating PDF for order {order.id}: {e}")
        # return None
        raise

def send_payment_success_email(order_id):
    try:
        order = Order.objects.get(id=order_id)
        user_email = order.user.email
        
        subject = f"Payment Successful - Your Invoice for Order #{order.order_id}"
        site_url = 'https://www.wacampaignsender.com'
        context = {
            'order': order, 
            'user': order.user,
            'site_url': site_url
        }
        html_content = render_to_string('userpanel/email/payment_successful.html', context)
        
        try:
            text_content = render_to_string('userpanel/email/payment_successful.txt', context)
        except Exception:
            # Fallback: simple line if txt template missing
            text_content = f"Thank you for your payment. Your order {order.order_id} has been processed successfully."
        
        email = EmailMultiAlternatives(
            subject,
            text_content,
            settings.DEFAULT_FROM_EMAIL,
            [user_email]
        )
        email.attach_alternative(html_content, "text/html")

        pdf_content = generate_invoice_pdf_for_email(order)
        if pdf_content:
            email.attach(f'Invoice-{order.order_id}.pdf', pdf_content, 'application/pdf')
        else:
            logger.warning(f"Could not attach PDF for order {order.id} to success email.")

        email.send()
        logger.info(f"Payment success email sent for order {order.id} to {user_email}")
    except Order.DoesNotExist:
        logger.error(f"Order with id {order_id} not found for sending success email.")
    except Exception as e:
        logger.error(f"Error sending payment success email for order {order_id}: {e}")
        raise

def send_payment_failure_email(user_email, order_invoice_id, payment_status, reason=""):
    try:
        subject = f"Payment Issue for Order #{order_invoice_id}"
        site_url = 'https://www.wacampaignsender.com' # Official domain
        context = {
            'order_invoice_id': order_invoice_id, 
            'payment_status': payment_status,
            'reason': reason,
            'site_url': site_url 
        }
        html_content = render_to_string('userpanel/email/payment_failed.html', context)
        
        try:
            text_content = render_to_string('userpanel/email/payment_failed.txt', context)
        except Exception:
            text_content = f"There was an issue with your payment for order {order_invoice_id}. Status: {payment_status}."
        
        email = EmailMultiAlternatives(
            subject,
            text_content,
            settings.DEFAULT_FROM_EMAIL,
            [user_email]
        )
        email.attach_alternative(html_content, "text/html")
        email.send()
        logger.info(f"Payment failure email sent for order/invoice {order_invoice_id} to {user_email}")
    except Exception as e:
        logger.error(f"Error sending payment failure email for order/invoice {order_invoice_id}: {e}")
