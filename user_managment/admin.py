from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import *



class CustomUserAdmin(UserAdmin):
    fieldsets = (
        # (None, {'fields': ('username', 'password')}),
        ('Personal info', {'fields': ('first_name', 'middle_name', 'last_name',  'phone', 'photo',)}),
        ('Permissions', {'fields': ('role','is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),  # Use exact model field names
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
        ('Status', {'fields': ('enabled', 'status')}),  # Use 'enabled' and 'status' as per the model fields
        ('Other info', {'fields': ('created', 'isLoggedIn')}),  # Match 'created' and 'isLoggedIn' field names from model
    )
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('first_name', 'last_name','middle_name', 'email','role', 'password1', 'password2', 'phone', 'photo', 'enabled', 'status', ),  # Ensure field names match the model fields
        }),
    )
    
    list_display = ( 'first_name','middle_name','email','role',"is_active" ,'enabled', 'is_staff')  # Match 'enabled' from model
    search_fields = ('email', 'first_name', 'last_name','phone')
    ordering = ('created',)

admin.site.register(User, CustomUserAdmin)

@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')
    search_fields = ('name',)

@admin.register(UserRole)
class UserRoleAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'role')
    search_fields = ('user__username', 'role__name')
    list_filter = ('role',)
    raw_id_fields = ('user',)
    
@admin.register(UserLog)
class UserLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'action', 'timestamp', 'ip_address')
    list_filter = ('action', 'timestamp', 'user')    

@admin.register(EmailOTP)
class EmailOTPAdmin(admin.ModelAdmin):
    list_display = ("user", "code", "resend_count", "created_at", "is_expired_display")
    search_fields = ("user__email", "code")
    list_filter = ("created_at", "resend_count")
    readonly_fields = ("created_at",)

    fieldsets = (
        (None, {
            "fields": ("user", "code", "resend_count")
        }),
        ("Metadata", {
            "fields": ("created_at",),
            "classes": ("collapse",),
        }),
    )

    def is_expired_display(self, obj):
        return obj.is_expired()
    is_expired_display.boolean = True
    is_expired_display.short_description = "Expired?"
