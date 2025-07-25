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

@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'date_joined', 'free_trial_start', 'free_trial_end', 'on_free_trial')
    list_filter = ('free_trial_start', 'free_trial_end')
    search_fields = ('user__email', 'user__full_name')
    readonly_fields = ('date_joined',)

@admin.register(WhatsAppNumber)
class WhatsAppNumberAdmin(admin.ModelAdmin):
    list_display = ('number', 'profile', 'is_verified', 'is_primary', 'is_active', 'created_at')
    list_filter = ('is_verified', 'is_primary', 'is_active')
    search_fields = ('number', 'profile__user__email')

@admin.register(FreeTrialPhone)
class FreeTrialPhoneAdmin(admin.ModelAdmin):
    list_display = ('phone', 'user', 'used_at')
    list_filter = ('used_at',)
    search_fields = ('phone', 'user__email')
    readonly_fields = ('used_at',)

@admin.register(NewsletterSubscriber)
class NewsletterSubscriberAdmin(admin.ModelAdmin):
    list_display = ('email', 'subscribed_at')
    list_filter = ('subscribed_at',)
    search_fields = ('email',)
    readonly_fields = ('subscribed_at',)

@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'subject', 'timestamp', 'is_read')
    list_filter = ('is_read', 'timestamp')
    search_fields = ('name', 'email', 'subject')
    readonly_fields = ('timestamp',)

admin.site.register(CustomUser, CustomUserAdmin)
admin.site.register(EmailVerification)
admin.site.register(PasswordReset)
admin.site.register(OTPVerification)