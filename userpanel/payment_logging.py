"""
Enhanced PayPal Payment Logging System
Provides comprehensive logging for payment events with structured data
"""

import logging
import json
from django.utils import timezone
from django.conf import settings

# Configure payment-specific logger
payment_logger = logging.getLogger('paypal_payments')

class PaymentLogger:
    """
    Centralized payment logging with structured data and context
    """
    
    @staticmethod
    def log_payment_start(user, plan_type, amount, payment_method='PayPal'):
        """Log payment initiation"""
        payment_logger.info(
            "Payment process started",
            extra={
                'event_type': 'payment_start',
                'user_id': user.id,
                'user_email': user.email,
                'plan_type': plan_type,
                'amount': str(amount),
                'payment_method': payment_method,
                'timestamp': timezone.now().isoformat(),
                'environment': 'sandbox' if settings.DEBUG else 'production'
            }
        )
    
    @staticmethod
    def log_payment_verification(order_id, capture_id, verification_result, amount=None):
        """Log PayPal payment verification"""
        payment_logger.info(
            f"Payment verification {'successful' if verification_result else 'failed'}",
            extra={
                'event_type': 'payment_verification',
                'order_id': order_id,
                'capture_id': capture_id,
                'verification_result': verification_result,
                'amount': str(amount) if amount else None,
                'timestamp': timezone.now().isoformat(),
                'environment': 'sandbox' if settings.DEBUG else 'production'
            }
        )
    
    @staticmethod
    def log_payment_success(user, order, processing_time_ms=None):
        """Log successful payment completion"""
        payment_logger.info(
            "Payment completed successfully",
            extra={
                'event_type': 'payment_success',
                'user_id': user.id,
                'user_email': user.email,
                'order_id': order.order_id,
                'amount': str(order.total),
                'payment_method': order.payment_method,
                'paypal_payment_id': order.paypal_payment_id,
                'paypal_txn_id': order.paypal_txn_id,
                'processing_time_ms': processing_time_ms,
                'timestamp': timezone.now().isoformat(),
                'environment': 'sandbox' if settings.DEBUG else 'production'
            }
        )
    
    @staticmethod
    def log_payment_failure(user, error_type, error_message, context=None):
        """Log payment failure with detailed context"""
        payment_logger.error(
            f"Payment failed: {error_type}",
            extra={
                'event_type': 'payment_failure',
                'user_id': user.id if user else None,
                'user_email': user.email if user else None,
                'error_type': error_type,
                'error_message': error_message,
                'context': context or {},
                'timestamp': timezone.now().isoformat(),
                'environment': 'sandbox' if settings.DEBUG else 'production'
            }
        )
    
    @staticmethod
    def log_subscription_activation(user, subscription, order):
        """Log subscription activation"""
        payment_logger.info(
            "Subscription activated",
            extra={
                'event_type': 'subscription_activation',
                'user_id': user.id,
                'user_email': user.email,
                'subscription_id': subscription.id,
                'subscription_status': subscription.status,
                'subscription_end_date': subscription.end_date.isoformat() if subscription.end_date else None,
                'order_id': order.order_id,
                'amount': str(order.total),
                'timestamp': timezone.now().isoformat(),
                'environment': 'sandbox' if settings.DEBUG else 'production'
            }
        )
    
    @staticmethod
    def log_race_condition_detected(user, context):
        """Log race condition detection"""
        payment_logger.warning(
            "Race condition detected in payment processing",
            extra={
                'event_type': 'race_condition',
                'user_id': user.id,
                'user_email': user.email,
                'context': context,
                'timestamp': timezone.now().isoformat(),
                'environment': 'sandbox' if settings.DEBUG else 'production'
            }
        )
    
    @staticmethod
    def log_security_event(event_type, user, details):
        """Log security-related events"""
        payment_logger.warning(
            f"Security event: {event_type}",
            extra={
                'event_type': 'security_event',
                'security_event_type': event_type,
                'user_id': user.id if user else None,
                'user_email': user.email if user else None,
                'details': details,
                'timestamp': timezone.now().isoformat(),
                'environment': 'sandbox' if settings.DEBUG else 'production'
            }
        )
    
    @staticmethod
    def log_payment_recovery(order_id, user, recovery_type, success):
        """Log payment recovery attempts"""
        payment_logger.info(
            f"Payment recovery {'successful' if success else 'failed'}",
            extra={
                'event_type': 'payment_recovery',
                'recovery_type': recovery_type,
                'order_id': order_id,
                'user_id': user.id,
                'user_email': user.email,
                'success': success,
                'timestamp': timezone.now().isoformat(),
                'environment': 'sandbox' if settings.DEBUG else 'production'
            }
        )

# Utility functions for common logging scenarios

def log_paypal_api_call(endpoint, method, status_code, response_time_ms=None, error=None):
    """Log PayPal API calls for monitoring"""
    payment_logger.info(
        f"PayPal API call: {method} {endpoint}",
        extra={
            'event_type': 'paypal_api_call',
            'endpoint': endpoint,
            'method': method,
            'status_code': status_code,
            'response_time_ms': response_time_ms,
            'error': str(error) if error else None,
            'timestamp': timezone.now().isoformat(),
            'environment': 'sandbox' if settings.DEBUG else 'production'
        }
    )

def log_csrf_validation(user, request_path, success, error=None):
    """Log CSRF validation events"""
    payment_logger.info(
        f"CSRF validation {'successful' if success else 'failed'}",
        extra={
            'event_type': 'csrf_validation',
            'user_id': user.id if user else None,
            'user_email': user.email if user else None,
            'request_path': request_path,
            'success': success,
            'error': str(error) if error else None,
            'timestamp': timezone.now().isoformat(),
            'environment': 'sandbox' if settings.DEBUG else 'production'
        }
    )

def log_input_validation(user, field_name, validation_type, success, value=None):
    """Log input validation events"""
    payment_logger.info(
        f"Input validation: {field_name} - {'passed' if success else 'failed'}",
        extra={
            'event_type': 'input_validation',
            'user_id': user.id if user else None,
            'user_email': user.email if user else None,
            'field_name': field_name,
            'validation_type': validation_type,
            'success': success,
            'value': str(value)[:50] if value and success else None,  # Log first 50 chars if successful
            'timestamp': timezone.now().isoformat(),
            'environment': 'sandbox' if settings.DEBUG else 'production'
        }
    )

# Performance monitoring
class PaymentPerformanceLogger:
    """
    Monitor payment processing performance
    """
    
    def __init__(self, operation_name):
        self.operation_name = operation_name
        self.start_time = None
    
    def __enter__(self):
        self.start_time = timezone.now()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.start_time:
            duration_ms = (timezone.now() - self.start_time).total_seconds() * 1000
            
            payment_logger.info(
                f"Performance: {self.operation_name}",
                extra={
                    'event_type': 'performance_metric',
                    'operation': self.operation_name,
                    'duration_ms': round(duration_ms, 2),
                    'success': exc_type is None,
                    'error_type': exc_type.__name__ if exc_type else None,
                    'timestamp': timezone.now().isoformat(),
                    'environment': 'sandbox' if settings.DEBUG else 'production'
                }
            )

# Usage examples:
# 
# # Basic payment logging
# PaymentLogger.log_payment_start(user, 'PRO_MEMBERSHIP_1_MONTH', 5.99)
# PaymentLogger.log_payment_success(user, order, processing_time_ms=1250)
# 
# # Performance monitoring
# with PaymentPerformanceLogger('paypal_payment_verification'):
#     # Payment verification code here
#     pass
# 
# # API call logging
# log_paypal_api_call('/v2/checkout/orders/123', 'GET', 200, response_time_ms=450)
