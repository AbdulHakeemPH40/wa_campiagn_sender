from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.core.paginator import Paginator
from django.db.models import Q, Count, Sum, OuterRef, Subquery
from django.db.models.functions import TruncDay, TruncMonth, ExtractYear, ExtractMonth, ExtractDay
from django.utils import timezone
from django.conf import settings
from datetime import datetime, timedelta
from django.contrib.auth import logout
from django.db import transaction
import json
import csv
from sitevisitor.models import CustomUser, Profile, ContactMessage, NewsletterSubscriber
from .models import Subscription, Payment, Invoice, SubscriptionPlan
from .forms import GrantSubscriptionForm
from userpanel.models import WASenderSession
from whatsappapi.wasender_service import WASenderService

def is_admin_user(user):
    return user.is_authenticated and (user.is_staff or user.is_superuser)

@user_passes_test(is_admin_user)
def admin_dashboard_view(request):
    total_users = CustomUser.objects.count()
    active_subscriptions = Subscription.objects.filter(status='active').count()
    first_day_of_month = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    new_users_this_month = CustomUser.objects.filter(date_joined__gte=first_day_of_month).count()
    subscription_rate = round((active_subscriptions / total_users) * 100) if total_users > 0 else 0
    current_month_payments = Payment.objects.filter(status='completed', payment_date__gte=first_day_of_month)
    
    # Calculate revenue by currency (USD and INR separately)
    monthly_revenue_usd = round(current_month_payments.filter(currency='USD').aggregate(Sum('amount'))['amount__sum'] or 0, 2)
    monthly_revenue_inr = round(current_month_payments.filter(currency='INR').aggregate(Sum('amount'))['amount__sum'] or 0, 2)
    
    previous_month = first_day_of_month - timedelta(days=1)
    previous_month_start = previous_month.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    previous_month_payments = Payment.objects.filter(status='completed', payment_date__gte=previous_month_start, payment_date__lt=first_day_of_month)
    
    previous_monthly_revenue_usd = round(previous_month_payments.filter(currency='USD').aggregate(Sum('amount'))['amount__sum'] or 0, 2)
    previous_monthly_revenue_inr = round(previous_month_payments.filter(currency='INR').aggregate(Sum('amount'))['amount__sum'] or 0, 2)
    
    revenue_change_usd = round(((monthly_revenue_usd - previous_monthly_revenue_usd) / previous_monthly_revenue_usd) * 100) if previous_monthly_revenue_usd > 0 else (100 if monthly_revenue_usd > 0 else 0)
    revenue_change_inr = round(((monthly_revenue_inr - previous_monthly_revenue_inr) / previous_monthly_revenue_inr) * 100) if previous_monthly_revenue_inr > 0 else (100 if monthly_revenue_inr > 0 else 0)
    
    recent_activities = []
    recent_subscriptions = Subscription.objects.order_by('-created_at')[:5]
    for subscription in recent_subscriptions:
        recent_activities.append({
            'user': subscription.user,
            'action': f"New {subscription.plan} subscription",
            'action_type': 'subscription',
            'timestamp': subscription.created_at
        })
    recent_payments = Payment.objects.filter(status='completed').order_by('-payment_date')[:5]
    for payment in recent_payments:
        recent_activities.append({
            'user': payment.user,
            'action': f"Payment of ${payment.amount}",
            'action_type': 'payment',
            'timestamp': payment.payment_date
        })
    recent_activities = sorted(recent_activities, key=lambda x: x['timestamp'], reverse=True)[:10]
    
    # Chart data
    end_date = timezone.now()
    start_date = end_date - timedelta(days=180)
    plans = SubscriptionPlan.objects.all()
    months = []
    current_month_start = start_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end_month_start = end_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    while current_month_start <= end_month_start:
        months.append(current_month_start.strftime('%b %Y'))
        if current_month_start.month == 12:
            current_month_start = current_month_start.replace(year=current_month_start.year + 1, month=1)
        else:
            current_month_start = current_month_start.replace(month=current_month_start.month + 1)
    
    datasets = []
    colors = ['#9CA3AF', '#25D366', '#3B82F6']
    for i, plan in enumerate(plans):
        subscriptions_by_month = Subscription.objects.filter(
            plan=plan,
            created_at__gte=start_date,
            created_at__lte=end_date
        ).annotate(
            year=ExtractYear('created_at'),
            month_num=ExtractMonth('created_at')
        ).values('year', 'month_num').annotate(
            count=Count('id')
        ).order_by('year', 'month_num')
        
        subscription_counts = {}
        for item in subscriptions_by_month:
            if item['year'] and item['month_num']:
                dt = datetime(item['year'], item['month_num'], 1)
                subscription_counts[dt.strftime('%b %Y')] = item['count']
        dataset = {
            'label': f"{plan.name} Plan",
            'data': [subscription_counts.get(month, 0) for month in months],
            'borderColor': colors[i % len(colors)],
            'backgroundColor': colors[i % len(colors)].replace(')', ', 0.1)').replace('rgb', 'rgba'),
            'tension': 0.4,
            'fill': True
        }
        datasets.append(dataset)
    
    subscription_data = {'labels': months, 'datasets': datasets}
    
    context = {
        'total_users': total_users,
        'active_subscriptions': active_subscriptions,
        'new_users_this_month': new_users_this_month,
        'subscription_rate': subscription_rate,
        'monthly_revenue_usd': monthly_revenue_usd,
        'monthly_revenue_inr': monthly_revenue_inr,
        'revenue_change_usd': revenue_change_usd,
        'revenue_change_inr': revenue_change_inr,
        'recent_activities': recent_activities,
        'subscription_data': json.dumps(subscription_data)
    }
    return render(request, 'admin_panel/dashboard.html', context)

@user_passes_test(is_admin_user)
def admin_users_view(request):
    # Handle POST requests for bulk actions
    if request.method == 'POST':
        action = request.POST.get('action')
        selected_users = request.POST.getlist('selected_users')
        
        if not selected_users:
            messages.error(request, 'No users selected')
            return redirect('admin_panel:users')
        
        users = CustomUser.objects.filter(id__in=selected_users)
        
        if action == 'activate':
            users.update(is_active=True)
            messages.success(request, f'{len(users)} users activated')
        elif action == 'deactivate':
            users.update(is_active=False)
            messages.success(request, f'{len(users)} users deactivated')
        elif action == 'verify':
            users.update(is_email_verified=True)
            messages.success(request, f'{len(users)} users verified')
        elif action == 'export':
            return export_users_to_csv(users)
        
        return redirect('admin_panel:users')

    # Handle GET requests for listing users
    queryset = CustomUser.objects.all()
    
    # Apply filters
    search_query = request.GET.get('search', '')
    status_filter = request.GET.get('status', '')
    
    if search_query:
        queryset = queryset.filter(
            Q(email__icontains=search_query) | 
            Q(full_name__icontains=search_query)
        )
    
    if status_filter == 'active':
        queryset = queryset.filter(is_active=True)
    elif status_filter == 'inactive':
        queryset = queryset.filter(is_active=False)
    elif status_filter == 'verified':
        queryset = queryset.filter(is_email_verified=True)
    elif status_filter == 'unverified':
        queryset = queryset.filter(is_email_verified=False)
    
    queryset = queryset.order_by('-date_joined')

    # Pagination
    paginator = Paginator(queryset, 20)
    page_number = request.GET.get('page')
    users = paginator.get_page(page_number)

    # Attach subscription info to each user
    for user in users:
        subscription = Subscription.objects.filter(user=user, status='active').select_related('plan').first()
        if subscription:
            if subscription.plan:
                plan_name = subscription.plan.name
                if '1 Month' in plan_name:
                    plan_name = '1-Month Plan'
                elif '6 Month' in plan_name or '6 Months' in plan_name:
                    plan_name = '6-Month Plan'
            else:
                if subscription.end_date and subscription.created_at:
                    delta_days = (subscription.end_date - subscription.created_at).days
                    plan_name = '6-Month Plan' if delta_days > 60 else '1-Month Plan'
                else:
                    plan_name = '1-Month Plan'
            end_date_str = subscription.end_date.strftime('%Y-%m-%d') if subscription.end_date else 'N/A'
            user.subscription_info = f"{plan_name} (until {end_date_str})"
        else:
            user.subscription_info = None

    context = {
        'users': users,
        'search_query': search_query,
        'status_filter': status_filter,
        'total_users': CustomUser.objects.count(),
        'active_users': CustomUser.objects.filter(is_active=True).count(),
        'verified_users': CustomUser.objects.filter(is_email_verified=True).count(),
        'users_with_subscription': Subscription.objects.filter(status='active').values('user').distinct().count()
    }
    
    return render(request, 'admin_panel/users.html', context)

def export_users_to_csv(users):
    """Helper function to export users to CSV"""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="users.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['Email', 'Full Name', 'Date Joined', 'Active', 'Verified', 'Subscription'])
    
    for user in users:
        subscription = Subscription.objects.filter(user=user, status='active').select_related('plan').first()
        if subscription:
            plan_name = subscription.plan.name if subscription.plan else 'Unknown Plan'
            end_date_str = subscription.end_date.strftime('%Y-%m-%d') if subscription.end_date else 'N/A'
            subscription_info = f"{plan_name} (until {end_date_str})"
        else:
            subscription_info = "None"

        full_name = getattr(user, 'full_name', '') or user.get_full_name() or user.username
        
        writer.writerow([
            user.email,
            full_name,
            user.date_joined.strftime('%Y-%m-%d'),
            'Yes' if user.is_active else 'No',
            'Yes' if user.is_email_verified else 'No',
            subscription_info
        ])
    
    return response

@user_passes_test(is_admin_user)
def export_all_users_csv(request):
    """Export all users data to CSV"""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="all_users_data.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['Email', 'Full Name', 'Phone Number', 'Date Joined', 'Status', 'Email Verified', 'Current Plan', 'Subscription End'])
    
    users = CustomUser.objects.all().order_by('-date_joined')
    
    for user in users:
        # Phone number removed (using WASender API Integration)
        phone_number = ''
        
        # Get subscription info
        subscription = Subscription.objects.filter(user=user, status='active').select_related('plan').first()
        if subscription:
            current_plan = subscription.plan.name if subscription.plan else 'Unknown Plan'
            subscription_end = subscription.end_date.strftime('%Y-%m-%d') if subscription.end_date else 'N/A'
        else:
            current_plan = 'None'
            subscription_end = 'N/A'
        
        writer.writerow([
            user.email,
            user.full_name or '',
            phone_number,
            user.date_joined.strftime('%Y-%m-%d %H:%M'),
            'Active' if user.is_active else 'Inactive',
            'Yes' if user.is_email_verified else 'No',
            current_plan,
            subscription_end
        ])
    
    return response

@user_passes_test(is_admin_user)
def admin_user_detail_view(request, pk):
    user_obj = get_object_or_404(CustomUser, pk=pk)
    profile, _ = Profile.objects.get_or_create(user=user_obj)

    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'activate':
            user_obj.is_active = True
            user_obj.save()
            messages.success(request, f'User {user_obj.email} activated')
        elif action == 'deactivate':
            user_obj.is_active = False
            user_obj.save()
            messages.success(request, f'User {user_obj.email} deactivated')
        elif action == 'verify':
            user_obj.is_email_verified = True
            user_obj.save()
            messages.success(request, f'User {user_obj.email} verified')
        elif action == 'cancel_subscription':
            subscription_id = request.POST.get('subscription_id')
            subscription = get_object_or_404(Subscription, id=subscription_id, user=user_obj)
            
            subscription.cancel(reason='Admin initiated cancellation')
            messages.success(request, f'Subscription cancelled')
        
        return redirect('admin_panel:user_detail', pk=pk)

    # GET request context
    context = {
        'user_obj': user_obj,
        'profile': profile,
        'subscriptions': Subscription.objects.filter(user=user_obj).order_by('-created_at'),
        'payments': Payment.objects.filter(user=user_obj).order_by('-payment_date'),
        'invoices': Invoice.objects.filter(user=user_obj).order_by('-created_at')
    }
    return render(request, 'admin_panel/user_detail.html', context)

@user_passes_test(is_admin_user)
def admin_subscriptions_view(request):
    from .models import Subscription, SubscriptionPlan, Payment
    from django.core.paginator import Paginator
    from django.db.models import Q, Sum
    from django.utils import timezone
    import json
    
    # Helper function for chart data
    def get_subscription_chart_data():
        end_date = timezone.now()
        start_date = end_date - timedelta(days=30)
        
        # Use Extract functions instead of TruncDay to avoid MySQL timezone issues
        subscriptions_by_day = Subscription.objects.filter(
            created_at__gte=start_date,
            created_at__lte=end_date
        ).annotate(
            year=ExtractYear('created_at'),
            month=ExtractMonth('created_at'),
            day_num=ExtractDay('created_at')
        ).values('year', 'month', 'day_num').annotate(
            count=Count('id')
        ).order_by('year', 'month', 'day_num')
        
        # Build a lookup dict for quick access
        day_lookup = {}
        for item in subscriptions_by_day:
            if item['year'] and item['month'] and item['day_num']:
                key = f"{item['year']}-{item['month']:02d}-{item['day_num']:02d}"
                day_lookup[key] = item['count']
        
        days = []
        day_counts = []
        current_date = start_date
        while current_date <= end_date:
            date_key = current_date.strftime('%Y-%m-%d')
            days.append(date_key)
            day_counts.append(day_lookup.get(date_key, 0))
            current_date += timedelta(days=1)
        
        return {
            'labels': days,
            'datasets': [{
                'label': 'New Subscriptions',
                'data': day_counts,
                'borderColor': '#25D366',
                'backgroundColor': 'rgba(37, 211, 102, 0.1)',
                'tension': 0.4,
                'fill': True
            }]
        }

    # Handle POST requests for bulk actions
    if request.method == 'POST':
        action = request.POST.get('action')
        selected_subscriptions = request.POST.getlist('selected_subscriptions')
        
        if not selected_subscriptions:
            messages.error(request, 'No subscriptions selected')
            return redirect('admin_panel:subscriptions')
        
        subscriptions = Subscription.objects.filter(id__in=selected_subscriptions)
        
        if action == 'activate':
            subscriptions.update(status='active')
            messages.success(request, f'{len(subscriptions)} subscriptions activated')
        elif action == 'deactivate':
            subscriptions.update(status='inactive')
            messages.success(request, f'{len(subscriptions)} subscriptions deactivated')
        elif action == 'cancel':
            subscriptions.update(status='cancelled', end_date=timezone.now())
            messages.success(request, f'{len(subscriptions)} subscriptions cancelled')
        
        return redirect('admin_panel:subscriptions')

    # Handle GET requests for listing subscriptions
    queryset = Subscription.objects.all()
    
    # Apply filters
    search_query = request.GET.get('search', '')
    status_filter = request.GET.get('status', '')
    plan_filter = request.GET.get('plan', '')
    
    if search_query:
        queryset = queryset.filter(
            Q(user__email__icontains=search_query) | 
            Q(user__full_name__icontains=search_query) |
            Q(subscription_number__icontains=search_query)
        )
    
    if status_filter:
        queryset = queryset.filter(status=status_filter)
    
    if plan_filter:
        queryset = queryset.filter(plan_id=plan_filter)
    
    queryset = queryset.select_related('user', 'plan').order_by('-created_at')

    # Pagination
    paginator = Paginator(queryset, 20)
    page_number = request.GET.get('page')
    subscriptions = paginator.get_page(page_number)

    # Attach human-readable plan label for template if plan missing
    for sub in subscriptions:
        if not sub.plan:
            if sub.end_date and sub.created_at:
                delta_days = (sub.end_date - sub.created_at).days
                sub.plan_label = '6-Month Plan' if delta_days > 60 else '1-Month Plan'
        sub.is_expired = sub.end_date and sub.end_date < timezone.now()

    # Context data
    context = {
        'subscriptions': subscriptions,
        'search_query': search_query,
        'status_filter': status_filter,
        'plan_filter': plan_filter,
        'plans': SubscriptionPlan.objects.all(),
        'total_subscriptions': Subscription.objects.count(),
        'active_subscriptions': Subscription.objects.filter(status='active').count(),
        'cancelled_subscriptions': Subscription.objects.filter(status='cancelled').count(),
        'total_revenue': Payment.objects.filter(status='completed').aggregate(Sum('amount'))['amount__sum'] or 0,
        'subscription_data': json.dumps(get_subscription_chart_data())
    }
    
    return render(request, 'admin_panel/subscriptions.html', context)

@user_passes_test(is_admin_user)
def admin_subscription_detail_view(request, pk):
    subscription = get_object_or_404(Subscription, pk=pk)
    payments = Payment.objects.filter(subscription=subscription).order_by('-payment_date')

    context = {
        'subscription': subscription,
        'payments': payments,
    }
    return render(request, 'admin_panel/subscription_detail.html', context)

@user_passes_test(is_admin_user)
def admin_cancel_subscription_view(request, pk):
    subscription = get_object_or_404(Subscription, pk=pk)

    if request.method == 'POST':
        reason = request.POST.get('reason', '')
        subscription.cancel(reason=reason)
        messages.success(request, f'Subscription for {subscription.user.email} has been cancelled.')
        return redirect('admin_panel:subscription_detail', pk=subscription.pk)

    context = {
        'subscription': subscription,
    }
    return render(request, 'admin_panel/cancel_subscription.html', context)

@user_passes_test(is_admin_user)
def admin_payments_view(request):
    # Helper function for chart data
    def get_payment_chart_data():
        end_date = timezone.now()
        start_date = end_date - timedelta(days=30)
        
        # Use Extract functions instead of TruncDay to avoid MySQL timezone issues
        payments_by_day = Payment.objects.filter(
            payment_date__gte=start_date,
            payment_date__lte=end_date,
            status='completed'
        ).annotate(
            year=ExtractYear('payment_date'),
            month=ExtractMonth('payment_date'),
            day_num=ExtractDay('payment_date')
        ).values('year', 'month', 'day_num').annotate(
            total_amount=Sum('amount')
        ).order_by('year', 'month', 'day_num')
        
        # Build a lookup dict for quick access
        day_lookup = {}
        for item in payments_by_day:
            if item['year'] and item['month'] and item['day_num']:
                key = f"{item['year']}-{item['month']:02d}-{item['day_num']:02d}"
                day_lookup[key] = float(item['total_amount'] or 0)
        
        days = []
        day_amounts = []
        current_date = start_date
        while current_date <= end_date:
            date_key = current_date.strftime('%Y-%m-%d')
            days.append(date_key)
            day_amounts.append(day_lookup.get(date_key, 0))
            current_date += timedelta(days=1)
        
        return {
            'labels': days,
            'datasets': [{
                'label': 'Daily Revenue',
                'data': day_amounts,
                'borderColor': '#007bff',
                'backgroundColor': 'rgba(0, 123, 255, 0.1)',
                'tension': 0.4,
                'fill': True
            }]
        }

    # Helper function for CSV export
    def export_payments_to_csv(payments):
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="payments.csv"'
        
        writer = csv.writer(response)
        writer.writerow(['Date', 'Transaction ID', 'User', 'Amount', 'Status'])
        
        for payment in payments:
            writer.writerow([
                payment.payment_date.strftime('%Y-%m-%d'),
                payment.transaction_id,
                payment.user.email,
                payment.amount,
                payment.status
            ])
        
        return response

    # Handle POST requests for bulk actions
    if request.method == 'POST':
        action = request.POST.get('action')
        selected_payments = request.POST.getlist('selected_payments')
        
        if not selected_payments:
            messages.error(request, 'No payments selected')
            return redirect('admin_panel:payments')
        
        payments = Payment.objects.filter(id__in=selected_payments)
        
        if action == 'export':
            return export_payments_to_csv(payments)
        
        return redirect('admin_panel:payments')
    
    # Handle GET requests for listing payments
    queryset = Payment.objects.all()
    
    # Apply filters
    search_query = request.GET.get('search', '')
    status_filter = request.GET.get('status', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    
    if search_query:
        queryset = queryset.filter(
            Q(user__email__icontains=search_query) | 
            Q(transaction_id__icontains=search_query)
        )
    
    if status_filter:
        queryset = queryset.filter(status=status_filter)
    
    if date_from:
        try:
            date_from_parsed = datetime.strptime(date_from, '%Y-%m-%d').date()
            queryset = queryset.filter(payment_date__date__gte=date_from_parsed)
        except ValueError:
            pass
    
    if date_to:
        try:
            date_to_parsed = datetime.strptime(date_to, '%Y-%m-%d').date()
            queryset = queryset.filter(payment_date__date__lte=date_to_parsed)
        except ValueError:
            pass
    
    queryset = queryset.select_related('user', 'subscription').order_by('-payment_date')

    # Pagination
    paginator = Paginator(queryset, 20)
    page_number = request.GET.get('page')
    payments = paginator.get_page(page_number)

    # Context data
    context = {
        'payments': payments,
        'search_query': search_query,
        'status_filter': status_filter,
        'date_from': date_from,
        'date_to': date_to,
        'total_payments': Payment.objects.count(),
        'completed_payments': Payment.objects.filter(status='completed').count(),
        'failed_payments': Payment.objects.filter(status='failed').count(),
        'payment_data': json.dumps(get_payment_chart_data())
    }

    return render(request, 'admin_panel/payments.html', context)

@user_passes_test(is_admin_user)
def admin_invoices_view(request):
    search_query = request.GET.get('search', '')
    invoices = Invoice.objects.select_related('user', 'payment').all()

    if search_query:
        invoices = invoices.filter(
            Q(user__email__icontains=search_query) |
            Q(invoice_number__icontains=search_query)
        )

    invoices = invoices.order_by('-created_at')

    paginator = Paginator(invoices, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'search_query': search_query,
    }
    return render(request, 'admin_panel/invoices.html', context)

@user_passes_test(is_admin_user)
def admin_plans_view(request):
    plans = SubscriptionPlan.objects.all().order_by('price')

    context = {
        'plans': plans,
    }
    return render(request, 'admin_panel/plans.html', context)

@user_passes_test(is_admin_user)
def admin_grant_subscription_view(request):
    """Grant subscription or free trial to users"""
    from .forms import UserSearchForm, GrantSubscriptionForm
    
    search_form = UserSearchForm(request.GET or None)
    grant_form = GrantSubscriptionForm(request.POST or None)
    users = None
    selected_user = None
    
    # Search users
    if request.GET.get('q'):
        query = request.GET.get('q', '').strip()
        if query:
            # Search by email only (phone search removed due to model constraints)
            users = CustomUser.objects.filter(
                Q(email__icontains=query)
            ).select_related('profile').distinct()
            
            # Add subscription info to users
            users_list = []
            for user in users:
                user_data = user
                # Get active subscription
                active_sub = Subscription.objects.filter(
                    user=user, 
                    status='active',
                    end_date__gt=timezone.now()
                ).select_related('plan').first()
                
                if active_sub and active_sub.plan:
                    user_data.active_plan_name = active_sub.plan.name
                    user_data.subscription_end_date = active_sub.end_date
                    user_data.has_active_subscription = True
                else:
                    user_data.active_plan_name = '-'
                    user_data.subscription_end_date = None
                    user_data.has_active_subscription = False
                
                # Trial system removed (using subscription-based access only)
                user_data.trial_status = "N/A"
                
                # Phone numbers removed (using WASender API Integration)
                user_data.primary_phone = None
                user_data.linked_numbers = []
                
                users_list.append(user_data)
            
            users = users_list
    
    # Get selected user
    user_id = request.GET.get('user_id')
    if user_id:
        try:
            selected_user = CustomUser.objects.get(id=user_id)
        except CustomUser.DoesNotExist:
            messages.error(request, 'User not found')
            return redirect('admin_panel:grant_subscription')
    
    # Handle POST - Grant subscription
    if request.method == 'POST' and grant_form.is_valid():
        user_id = request.POST.get('user_id')
        try:
            user = CustomUser.objects.get(id=user_id)
            
            # Check if user already has an active subscription
            active_subscription = Subscription.objects.filter(
                user=user,
                status='active',
                end_date__gt=timezone.now()
            ).first()
            
            if active_subscription:
                plan_name = active_subscription.plan.name if active_subscription.plan else 'Unknown Plan'
                end_date_str = active_subscription.end_date.strftime('%Y-%m-%d %H:%M')
                messages.error(
                    request,
                    f"Cannot grant subscription: {user.email} already has an active subscription "
                    f"({plan_name}) valid until {end_date_str}. "
                    f"Please cancel or wait for the current subscription to expire before granting a new one."
                )
                return redirect(f"{reverse('admin_panel:grant_subscription')}?user_id={user_id}")
            
            plan = grant_form.cleaned_data['plan']
            
            if not plan:
                messages.error(request, 'Please select a subscription plan')
                return redirect(f"{reverse('admin_panel:grant_subscription')}?user_id={user_id}")
            
            # Calculate end date
            end_date = timezone.now() + timedelta(days=plan.duration_days)
            
            # Create subscription
            subscription = Subscription.objects.create(
                user=user,
                plan=plan,
                status='active',
                end_date=end_date,
                seats=1
            )
            
            messages.success(
                request,
                f"Successfully granted {plan.name} subscription to {user.email}. "
                f"Valid until {end_date.strftime('%Y-%m-%d')}"
            )
            
            return redirect('admin_panel:grant_subscription')
            
        except CustomUser.DoesNotExist:
            messages.error(request, 'User not found')
            return redirect('admin_panel:grant_subscription')
        except Exception as e:
            messages.error(request, f'Error granting access: {str(e)}')
            return redirect('admin_panel:grant_subscription')
    
    context = {
        'search_form': search_form,
        'grant_form': grant_form,
        'users': users,
        'selected_user': selected_user,
    }
    return render(request, 'admin_panel/grant_subscription.html', context)

@user_passes_test(is_admin_user)
def admin_settings_view(request):
    """Admin Settings – manage user service status."""

    # Handle inline actions: toggle block
    if request.method == 'POST':
        try:
            action = request.POST.get('action')
            user_id = request.POST.get('user_id')
            user = get_object_or_404(CustomUser, id=user_id)

            if action == 'toggle_block':
                with transaction.atomic():
                    user.is_active = not user.is_active
                    user.save(update_fields=['is_active'])
                    status_txt = 'unblocked' if user.is_active else 'blocked'
                    messages.success(request, f"User {user.email} has been {status_txt}.")
                    
        except Exception as e:
            messages.error(request, f"An error occurred: {str(e)}")
            
        return redirect('admin_panel:settings')

    # GET — list users with pagination
    queryset = CustomUser.objects.all().order_by('-date_joined')

    paginator = Paginator(queryset, 20)
    page_num = request.GET.get('page')
    users_page = paginator.get_page(page_num)

    # Attach helper info with error handling
    for usr in users_page:
        try:
            # Get subscription info only
            sub = Subscription.objects.filter(user=usr, status='active').select_related('plan').first()
            if sub and sub.plan:
                plan_name = sub.plan.name
                usr.subscription_display = plan_name
                usr.subscription_end = sub.end_date
            else:
                usr.subscription_display = 'None'
                usr.subscription_end = None
        except Exception as e:
            usr.subscription_display = 'Error'
            usr.subscription_end = None

    context = {
        'users': users_page,
    }
    return render(request, 'admin_panel/settings.html', context)

@user_passes_test(is_admin_user)
def contact_messages_view(request):
    search_query = request.GET.get('search', '')
    messages_list = ContactMessage.objects.all()

    if search_query:
        messages_list = messages_list.filter(
            Q(name__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(subject__icontains=search_query)
        )

    messages_list = messages_list.order_by('-timestamp')

    paginator = Paginator(messages_list, 20)
    page_number = request.GET.get('page')
    messages = paginator.get_page(page_number)

    context = {
        'messages': messages,
        'search_query': search_query,
    }
    return render(request, 'admin_panel/contact_messages.html', context)

@user_passes_test(is_admin_user)
def contact_message_detail_view(request, pk):
    message = get_object_or_404(ContactMessage, pk=pk)

    # Mark as read
    if not message.is_read:
        message.is_read = True
        message.save()

    context = {
        'message': message,
    }
    return render(request, 'admin_panel/contact_message_detail.html', context)

@user_passes_test(is_admin_user)
def newsletter_subscribers_view(request):
    search_query = request.GET.get('search', '')
    subscribers = NewsletterSubscriber.objects.all()

    if search_query:
        subscribers = subscribers.filter(email__icontains=search_query)

    subscribers = subscribers.order_by('-subscribed_at')

    paginator = Paginator(subscribers, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'search_query': search_query,
    }
    return render(request, 'admin_panel/newsletter_subscribers.html', context)

@user_passes_test(is_admin_user)
def unread_messages_api(request):
    unread_messages = ContactMessage.objects.filter(is_read=False).order_by('-timestamp')[:5]
    messages_data = []

    for message in unread_messages:
        messages_data.append({
            'id': message.id,
            'name': message.name,
            'subject': message.subject,
            'timestamp': message.timestamp.isoformat(),
        })

    return JsonResponse({'messages': messages_data})

@user_passes_test(is_admin_user)
def export_newsletter_subscribers(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="newsletter_subscribers.csv"'

    writer = csv.writer(response)
    writer.writerow(['Email', 'Subscribed Date'])

    subscribers = NewsletterSubscriber.objects.all().order_by('-subscribed_at')
    for subscriber in subscribers:
        writer.writerow([subscriber.email, subscriber.subscribed_at.strftime('%Y-%m-%d %H:%M:%S')])

    return response

@user_passes_test(is_admin_user)
def admin_logout_view(request):
    logout(request)
    return redirect('sitevisitor:home')

@user_passes_test(is_admin_user)
def admin_cancel_subscription_view(request, pk):
    subscription = get_object_or_404(Subscription, pk=pk)

    if request.method == 'POST':
        reason = request.POST.get('cancel_reason', 'Admin initiated cancellation')
        subscription.cancel(reason=reason)
        messages.success(request, f"Subscription for {subscription.user.email} has been successfully cancelled.")
        return redirect('admin_panel:subscriptions')

    context = {
        'subscription': subscription,
    }
    return render(request, 'admin_panel/cancel_subscription.html', context)

@user_passes_test(is_admin_user)
def admin_whatsapp_sessions_view(request):
    """
    Admin view to manage all WhatsApp sessions across all users
    """
    # Get all sessions with related user info
    sessions = WASenderSession.objects.select_related('user').order_by('-created_at')
    
    # Apply filters
    search_query = request.GET.get('search', '')
    status_filter = request.GET.get('status', '')
    
    if search_query:
        sessions = sessions.filter(
            Q(user__email__icontains=search_query) |
            Q(user__full_name__icontains=search_query) |
            Q(phone_number__icontains=search_query) |
            Q(session_id__icontains=search_query)
        )
    
    if status_filter:
        sessions = sessions.filter(status=status_filter)
    
    # Pagination
    paginator = Paginator(sessions, 20)
    page_number = request.GET.get('page')
    sessions_page = paginator.get_page(page_number)
    
    # Get status counts for filter buttons
    total_sessions = WASenderSession.objects.count()
    connected_count = WASenderSession.objects.filter(status='connected').count()
    pending_count = WASenderSession.objects.filter(status='pending').count()
    disconnected_count = WASenderSession.objects.filter(status='disconnected').count()
    
    context = {
        'sessions': sessions_page,
        'search_query': search_query,
        'status_filter': status_filter,
        'total_sessions': total_sessions,
        'connected_count': connected_count,
        'pending_count': pending_count,
        'disconnected_count': disconnected_count,
    }
    return render(request, 'admin_panel/whatsapp_sessions.html', context)

@user_passes_test(is_admin_user)
def admin_disconnect_session(request, session_id):
    """
    Admin action to disconnect a user's WhatsApp session
    """
    session = get_object_or_404(WASenderSession, id=session_id)
    
    if request.method == 'POST':
        service = WASenderService()
        success = service.disconnect_session(session)
        
        if success:
            messages.success(request, f"Successfully disconnected session for {session.user.email}")
        else:
            messages.error(request, f"Failed to disconnect session for {session.user.email}")
        
        return redirect('admin_panel:whatsapp_sessions')
    
    return redirect('admin_panel:whatsapp_sessions')

@user_passes_test(is_admin_user)
def admin_delete_session(request, session_id):
    """
    Admin action to delete a user's WhatsApp session completely
    """
    session = get_object_or_404(WASenderSession, id=session_id)
    
    if request.method == 'POST':
        service = WASenderService()
        user_email = session.user.email
        session_id_text = session.session_id
        
        # Try to disconnect first if connected
        if session.status == 'connected':
            service.disconnect_session(session)
        
        # Try to delete from WASender API
        # This returns True even if session doesn't exist (404)
        api_deleted = service.delete_session(session)
        
        # Always delete from local database
        # Even if API deletion failed, we should clean up our database
        session.delete()
        
        if api_deleted:
            messages.success(request, f"Successfully deleted session {session_id_text} for {user_email}")
        else:
            # API deletion failed but local deletion succeeded
            messages.warning(
                request, 
                f"Session {session_id_text} deleted from database, but WASender API deletion failed. "
                f"You may need to manually delete it from WASender dashboard."
            )
        
        return redirect('admin_panel:whatsapp_sessions')
    
    return redirect('admin_panel:whatsapp_sessions')
