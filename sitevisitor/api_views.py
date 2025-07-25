from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.contrib.auth import get_user_model
from adminpanel.models import Subscription
import json

User = get_user_model()

@csrf_exempt
def verify_license(request):
    # Handle CORS preflight
    if request.method == 'OPTIONS':
        response = JsonResponse({})
        response['Access-Control-Allow-Origin'] = '*'
        response['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
        response['Access-Control-Allow-Headers'] = 'Content-Type'
        return response
    
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    try:
        data = json.loads(request.body)
        phone_number = data.get('phone_number')
        
        if not phone_number:
            return JsonResponse({'error': 'Phone number required'}, status=400)
        
        # Clean and normalize phone number
        # Remove common prefixes and formatting
        clean_number = phone_number.replace('+', '').replace('-', '').replace(' ', '').replace('(', '').replace(')', '')
        
        # Try different formats - prioritize normalized format
        possible_numbers = [
            clean_number,  # Normalized format (no + prefix)
            phone_number,  # Original format
            '+' + clean_number,  # With + prefix
        ]
        
        # Find user by phone number - check both phone_number field and WhatsApp numbers
        user = None
        whatsapp_number_obj = None
        
        for number_variant in possible_numbers:
            try:
                user = User.objects.get(phone_number=number_variant)
                break
            except User.DoesNotExist:
                # Try to find user by WhatsApp number
                from sitevisitor.models import WhatsAppNumber
                try:
                    whatsapp_number_obj = WhatsAppNumber.objects.get(number=number_variant)
                    user = whatsapp_number_obj.profile.user
                    break
                except WhatsAppNumber.DoesNotExist:
                    continue
        
        if not user:
            response = JsonResponse({
                'is_active': False,
                'is_trial': False,
                'error': 'User not found. Please register first.'
            })
            response['Access-Control-Allow-Origin'] = '*'
            return response
        
        # Check user's profile for trial status
        try:
            profile = user.profile
        except:
            # Create profile if it doesn't exist
            from sitevisitor.models import Profile
            profile = Profile.objects.create(user=user)
        
        now = timezone.now().date()
        
        # Check if user is on free trial
        if profile.on_free_trial:
            days_remaining = (profile.free_trial_end - now).days
            response = JsonResponse({
                'is_active': True,
                'is_trial': True,
                'days_remaining': days_remaining,
                'user_id': user.id,
                'phone_number': phone_number
            })
            response['Access-Control-Allow-Origin'] = '*'
            return response
        
        # Check if user has active subscription (with expiry check)
        active_subscription = Subscription.objects.filter(
            user=user,
            status='active',
            end_date__gt=timezone.now()
        ).first()
        
        if active_subscription:
            # Determine plan type and limits
            from sitevisitor.models import WhatsAppNumber
            user_numbers = WhatsAppNumber.objects.filter(profile=profile).count()
            
            # Get plan info
            plan_name = 'Unknown'
            max_numbers = 3  # Default
            
            if active_subscription.plan:
                plan_name = active_subscription.plan.name
                if '1 month' in plan_name.lower():
                    max_numbers = 3
                elif '6 month' in plan_name.lower():
                    max_numbers = 6
                elif '1 year' in plan_name.lower():
                    max_numbers = 10
            else:
                # Admin granted subscription without plan
                max_numbers = 3
                plan_name = 'Admin Granted'
            
            response = JsonResponse({
                'is_active': True,
                'is_trial': False,
                'subscription_type': 'pro',
                'plan_name': plan_name,
                'numbers_used': user_numbers,
                'numbers_allowed': max_numbers,
                'user_id': user.id,
                'phone_number': phone_number
            })
            response['Access-Control-Allow-Origin'] = '*'
            return response
        
        # No active license
        response = JsonResponse({
            'is_active': False,
            'is_trial': False,
            'error': 'No active license found. Please purchase a subscription.'
        })
        response['Access-Control-Allow-Origin'] = '*'
        return response
        
    except json.JSONDecodeError:
        response = JsonResponse({
            'error': 'Invalid JSON format',
            'is_active': False,
            'is_trial': False
        }, status=400)
        response['Access-Control-Allow-Origin'] = '*'
        return response
    except Exception as e:
        # Log the error for debugging
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f'License verification error: {str(e)}')
        
        response = JsonResponse({
            'error': 'Internal server error. Please try again later.',
            'is_active': False,
            'is_trial': False
        }, status=500)
        response['Access-Control-Allow-Origin'] = '*'
        return response