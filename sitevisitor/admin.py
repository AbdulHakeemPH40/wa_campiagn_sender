from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.db import transaction
from .models import CustomUser, Profile, WhatsAppNumber, EmailVerification, PasswordReset, OTPVerification, FreeTrialPhone, NewsletterSubscriber, ContactMessage

class CustomUserAdmin(UserAdmin):
    model = CustomUser
    list_display = ('email', 'full_name', 'is_staff', 'is_active', 'date_joined')
    list_filter = ('is_staff', 'is_active', 'is_email_verified')
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal info', {'fields': ('full_name', 'phone_number')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
        ('Email verification', {'fields': ('is_email_verified',)}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'full_name', 'password1', 'password2'),
        }),
    )
    search_fields = ('email', 'full_name')
    ordering = ('email',)
    
    def delete_model(self, request, obj):
        """Custom delete method to handle foreign key constraints"""
        try:
            with transaction.atomic():
                # Delete related objects first
                Profile.objects.filter(user=obj).delete()
                WhatsAppNumber.objects.filter(profile__user=obj).delete()
                EmailVerification.objects.filter(user=obj).delete()
                PasswordReset.objects.filter(user=obj).delete()
                OTPVerification.objects.filter(user=obj).delete()
                
                # Delete from userpanel models
                from userpanel.models import Order, Address
                Order.objects.filter(user=obj).delete()
                Address.objects.filter(user=obj).delete()
                
                # Delete from adminpanel models
                from adminpanel.models import Subscription, Payment
                Subscription.objects.filter(user=obj).delete()
                Payment.objects.filter(user=obj).delete()
                
                # Finally delete the user
                super().delete_model(request, obj)
                
        except Exception as e:
            from django.contrib import messages
            messages.error(request, f"Error deleting user: {str(e)}")
    
    def delete_queryset(self, request, queryset):
        """Custom bulk delete method"""
        try:
            with transaction.atomic():
                for obj in queryset:
                    self.delete_model(request, obj)
        except Exception as e:
            from django.contrib import messages
            messages.error(request, f"Error deleting users: {str(e)}")

admin.site.register(CustomUser, CustomUserAdmin)
admin.site.register(Profile)
admin.site.register(WhatsAppNumber)
admin.site.register(EmailVerification)
admin.site.register(PasswordReset)
admin.site.register(OTPVerification)
admin.site.register(FreeTrialPhone)
admin.site.register(NewsletterSubscriber)
admin.site.register(ContactMessage)