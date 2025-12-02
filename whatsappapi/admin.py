from django.contrib import admin
from .models import ContactList, Contact


@admin.register(ContactList)
class ContactListAdmin(admin.ModelAdmin):
    list_display = ['name', 'user', 'file_name', 'total_contacts', 'valid_contacts', 'created_at']
    list_filter = ['created_at', 'user']
    search_fields = ['name', 'file_name', 'user__email']
    date_hierarchy = 'created_at'


@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ['phone_number', 'first_name', 'last_name', 'email', 'contact_list', 'is_on_whatsapp', 'created_at']
    list_filter = ['is_on_whatsapp', 'created_at', 'contact_list']
    search_fields = ['phone_number', 'first_name', 'last_name', 'email', 'custom_field_1', 'custom_field_2', 'custom_field_3']
    date_hierarchy = 'created_at'
