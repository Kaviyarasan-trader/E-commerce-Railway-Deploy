from django import forms
from django.contrib import admin, messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.urls import path, reverse
from django.utils.html import format_html
from io import BytesIO
import zipfile
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import UserChangeForm
from django.contrib.auth.models import User, Permission
from django.db.models import Q, Count, Sum, F
from django.db.models.functions import TruncMonth, TruncHour
from django.utils import timezone
from datetime import timedelta
import json
from .models import Catagory, Product, ProductImage, Cart, Favourite, Order, OrderItem, Payment, LoginOTP, UserProfile, SavedAddress, ProductRating, ProductRatingMedia, Notification, Invoice
from .utils import delete_image_file, collect_product_images
from .notifications import notify_product_back_in_stock, notify_product_price_drop


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    extra = 0


ADMIN_SECTION_PERMS = {
    'section_products': ('view_product', 'add_product', 'change_product', 'delete_product'),
    'section_categories': ('view_catagory', 'add_catagory', 'change_catagory', 'delete_catagory'),
    'section_orders': ('view_order', 'change_order'),
    'section_payments': ('view_payment',),
    'section_reviews': ('view_productrating', 'change_productrating', 'delete_productrating'),
    'section_low_stock': ('change_product',),
    'section_send_announcement': ('change_notification',),
}


class UserNavForm(UserChangeForm):
    section_dashboard = forms.BooleanField(
        required=False, label='Dashboard',
        help_text='Show the Dashboard in the KaviBazaar admin sidebar.')
    section_products = forms.BooleanField(required=False, label='Products')
    section_categories = forms.BooleanField(required=False, label='Categories')
    section_orders = forms.BooleanField(required=False, label='Orders')
    section_payments = forms.BooleanField(required=False, label='Payments')
    section_reviews = forms.BooleanField(required=False, label='Reviews')
    section_low_stock = forms.BooleanField(
        required=False, label='Low Stock',
        help_text='Manage product stock. Shares the change_product permission with Products.')
    section_send_announcement = forms.BooleanField(
        required=False, label='Send Announcement',
        help_text='Allow sending announcements to all users.')
    section_permissions = forms.BooleanField(
        required=False, label='Permissions',
        help_text='Make this admin a superuser (full access, shows the Permissions page).')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            codes = set(self.instance.user_permissions.filter(
                content_type__app_label='shop').values_list('codename', flat=True))
            profile = UserProfile.objects.filter(user=self.instance).first()
            self.fields['section_dashboard'].initial = bool(profile and profile.dashboard_access)
            self.fields['section_products'].initial = 'view_product' in codes
            self.fields['section_categories'].initial = 'view_catagory' in codes
            self.fields['section_orders'].initial = 'view_order' in codes
            self.fields['section_payments'].initial = 'view_payment' in codes
            self.fields['section_reviews'].initial = 'view_productrating' in codes
            self.fields['section_low_stock'].initial = 'change_product' in codes
            self.fields['section_send_announcement'].initial = 'change_notification' in codes
            self.fields['section_permissions'].initial = bool(self.instance.is_superuser)


class UserAdmin(BaseUserAdmin):
    inlines = [UserProfileInline]
    form = UserNavForm
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Personal info', {'fields': ('first_name', 'last_name', 'email')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'groups', 'user_permissions')}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    ) + (
        ('Admin Navigation Access', {
            'classes': ('admin-nav-section',),
            'description': 'Tick the sections this admin can access in the KaviBazaar admin. Permissions grants full superuser access.',
            'fields': ('section_dashboard', 'section_products', 'section_categories', 'section_orders', 'section_payments', 'section_reviews', 'section_low_stock', 'section_send_announcement', 'section_permissions'),
        }),
    )

    class Media:
        js = ('shop/admin_nav_perms.js',)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        user = form.instance
        dash_checked = bool(form.cleaned_data.get('section_dashboard', False))
        profile, _ = UserProfile.objects.get_or_create(user=user)
        if profile.dashboard_access != dash_checked:
            profile.dashboard_access = dash_checked
            profile.save(update_fields=['dashboard_access'])

        wanted = {
            codename
            for key, codenames in ADMIN_SECTION_PERMS.items()
            if key in form.cleaned_data and form.cleaned_data.get(key, False)
            for codename in codenames
        }
        all_codenames = {
            codename
            for codenames in ADMIN_SECTION_PERMS.values()
            for codename in codenames
        }
        for codename in all_codenames:
            perm = Permission.objects.get(codename=codename, content_type__app_label='shop')
            if codename in wanted:
                user.user_permissions.add(perm)
            else:
                user.user_permissions.remove(perm)

        is_super = bool(form.cleaned_data.get('section_permissions')) or bool(form.cleaned_data.get('is_superuser'))
        if user.is_superuser != is_super:
            user.is_superuser = is_super
            user.save(update_fields=['is_superuser'])


admin.site.unregister(User)
admin.site.register(User, UserAdmin)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'mobile_number', 'created_at')
    search_fields = ('user__username', 'user__email', 'mobile_number')


@admin.register(LoginOTP)
class LoginOTPAdmin(admin.ModelAdmin):
    list_display = ('identifier', 'is_used', 'attempts', 'created_at', 'expires_at', 'is_expired')
    list_filter = ('is_used',)
    search_fields = ('identifier',)
    readonly_fields = ('otp_hash',)
    ordering = ('-created_at',)


@admin.register(ProductRating)
class ProductRatingAdmin(admin.ModelAdmin):
    list_display = ('product', 'user', 'rating', 'comment', 'created_at')
    list_filter = ('rating',)
    search_fields = ('product__name', 'user__username', 'user__email')


@admin.register(ProductRatingMedia)
class ProductRatingMediaAdmin(admin.ModelAdmin):
    list_display = ('rating', 'media_type', 'file', 'created_at')
    list_filter = ('media_type',)


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ('product', 'quantity', 'price', 'get_total_cost')

    def get_total_cost(self, obj):
        if obj and obj.quantity and obj.price:
            return f"Rs. {obj.quantity * obj.price}"
        return "Rs. 0"
    get_total_cost.short_description = "Total"


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'total_amount', 'status', 'cancelled_reason', 'phone', 'alternate_phone', 'address', 'created_at')
    list_filter = ('status',)
    search_fields = ('user__username', 'phone', 'alternate_phone', 'address', 'cancel_reason')
    list_editable = ('status',)
    fields = ('user', 'total_amount', 'status', 'phone', 'alternate_phone', 'address', 'created_at', 'cancel_reason', 'cancelled_at')
    readonly_fields = ('user', 'total_amount', 'phone', 'alternate_phone', 'address', 'created_at', 'cancel_reason', 'cancelled_at')
    inlines = [OrderItemInline]
    ordering = ('-created_at',)

    def get_readonly_fields(self, request, obj=None):
        fields = list(super().get_readonly_fields(request, obj))
        if obj and obj.status == 'Cancelled' and obj.cancel_reason and 'status' not in fields:
            fields.append('status')
        return tuple(fields)

    def save_model(self, request, obj, form, change):
        if change and obj.pk:
            original = Order.objects.filter(pk=obj.pk).only('status', 'cancel_reason').first()
            if original and original.status == 'Cancelled' and original.cancel_reason:
                obj.status = 'Cancelled'
                self.message_user(
                    request,
                    f"Order #{obj.pk} was cancelled by the user and its status cannot be changed.",
                    level=messages.ERROR,
                )
        super().save_model(request, obj, form, change)

    def get_changelist_form(self, request, **kwargs):
        return OrderChangelistForm

    @admin.display(description='Cancelled Reason')
    def cancelled_reason(self, obj):
        if not obj.cancel_reason:
            return ''
        return obj.cancel_reason if len(obj.cancel_reason) <= 45 else obj.cancel_reason[:42] + '...'


class OrderChangelistForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = ('status',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.status == 'Cancelled' and self.instance.cancel_reason:
            self.fields['status'].disabled = True


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 3
    fields = ('image',)
    verbose_name_plural = 'Gallery Images (select several at once — extra rows fill automatically)'

    class Media:
        js = ('admin/js/gallery_multi.js',)


class CatagoryAdminForm(forms.ModelForm):
    remove_image = forms.BooleanField(
        required=False, label='Remove image',
        help_text='Tick this and save to delete the current image from disk.')

    class Meta:
        model = Catagory
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not (self.instance.pk and self.instance.image):
            self.fields['remove_image'].widget = forms.HiddenInput()
        else:
            self.fields['remove_image'].widget.attrs.update({'style': 'margin-top:6px;'})


class ProductAdminForm(forms.ModelForm):
    remove_image = forms.BooleanField(
        required=False, label='Remove cover image',
        help_text='Tick this and save to delete the current cover image from disk.')
    cash_on_delivery = forms.TypedChoiceField(
        label='Cash on Delivery',
        required=True,
        coerce=lambda v: str(v).lower() == 'true',
        choices=((True, 'Yes'), (False, 'No')),
        widget=forms.Select)

    class Meta:
        model = Product
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not (self.instance.pk and self.instance.product_image):
            self.fields['remove_image'].widget = forms.HiddenInput()
        else:
            self.fields['remove_image'].widget.attrs.update({'style': 'margin-top:6px;'})


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    form = ProductAdminForm
    list_display = ('name', 'category', 'selling_price', 'quantity', 'trending', 'cash_on_delivery', 'status')
    list_editable = ('trending', 'status', 'cash_on_delivery')
    list_filter = ('category', 'trending', 'status', 'cash_on_delivery')
    search_fields = ('name', 'vendor')
    inlines = [ProductImageInline]
    fieldsets = (
        (None, {'fields': ('category', 'name', 'vendor', 'product_image', 'remove_image')}),
        ('Pricing', {'fields': ('original_price', 'selling_price', 'quantity')}),
        ('Status', {'fields': ('status', 'trending', 'cash_on_delivery', 'description')}),
        ('Highlights', {'fields': ('highlight_1', 'highlight_2', 'highlight_3')}),
        ('Perk 1', {'fields': ('perk_1_title', 'perk_1_sub')}),
        ('Perk 2', {'fields': ('perk_2_title', 'perk_2_sub')}),
        ('Perk 3', {'fields': ('perk_3_title', 'perk_3_sub')}),
    )

    def save_model(self, request, obj, form, change):
        if change and form.cleaned_data.get('remove_image') and obj.product_image:
            obj.product_image = None
        old_qty = old_price = None
        if change and obj.pk:
            original = Product.objects.filter(pk=obj.pk).only('quantity', 'selling_price').first()
            if original:
                old_qty = original.quantity
                old_price = original.selling_price
        super().save_model(request, obj, form, change)
        if change:
            if old_qty is not None and old_qty <= 0 and obj.quantity > 0:
                notify_product_back_in_stock(obj)
            if old_price is not None and obj.selling_price < old_price:
                notify_product_price_drop(obj, old_price, obj.selling_price)

    def delete_model(self, request, obj):
        image_names = collect_product_images(obj)
        super().delete_model(request, obj)
        for image_name in image_names:
            delete_image_file(image_name)

    def delete_queryset(self, request, queryset):
        image_names = []
        for obj in queryset:
            image_names.extend(collect_product_images(obj))
        super().delete_queryset(request, queryset)
        for image_name in image_names:
            delete_image_file(image_name)


@admin.register(SavedAddress)
class SavedAddressAdmin(admin.ModelAdmin):
    list_display = ('user', 'label', 'address', 'locality', 'pincode', 'phone', 'updated_at')
    search_fields = ('user__username', 'label', 'address', 'locality', 'pincode', 'phone')
    list_filter = ('label',)


@admin.register(Catagory)
class CatagoryAdmin(admin.ModelAdmin):
    form = CatagoryAdminForm
    list_display = ('name', 'description', 'status')

    def save_model(self, request, obj, form, change):
        if change and form.cleaned_data.get('remove_image') and obj.image:
            obj.image = None
        super().save_model(request, obj, form, change)

    def delete_model(self, request, obj):
        image_name = obj.image.name if obj.image else None
        super().delete_model(request, obj)
        if image_name:
            delete_image_file(image_name)

    def delete_queryset(self, request, queryset):
        image_names = [obj.image.name for obj in queryset if obj.image]
        super().delete_queryset(request, queryset)
        for image_name in image_names:
            delete_image_file(image_name)


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ('id', 'user_display', 'product', 'product_qty', 'total_cost', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('user__username', 'user__email', 'product__name')
    autocomplete_fields = ('product',)
    list_select_related = ('user', 'product')

    @admin.display(description='User (Gmail)')
    def user_display(self, obj):
        email = obj.user.email or ''
        if email and obj.user.username != email:
            return f"{obj.user.username} · {email}"
        return obj.user.username or email


admin.site.register(Favourite)
admin.site.register(Payment)


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'order', 'customer_name', 'payment_method', 'grand_total', 'issued_date', 'download_pdf_link')
    list_filter = ('payment_method', 'payment_status', 'order_status', 'issued_date')
    search_fields = ('invoice_number', 'customer_name', 'customer_email', 'customer_phone', 'order__id')
    readonly_fields = (
        'order', 'invoice_number', 'issued_date', 'customer_name', 'customer_email', 'customer_phone',
        'delivery_address', 'order_date', 'payment_method', 'payment_status', 'order_status',
        'subtotal', 'total_discount', 'delivery_charge', 'tax_amount', 'grand_total', 'line_items',
    )
    ordering = ('-issued_date',)
    actions = ('download_selected_pdfs',)

    def get_urls(self):
        urls = super().get_urls()
        my_urls = [
            path('<int:invoice_id>/pdf/', self.admin_site.admin_view(self.download_pdf), name='shop_invoice_download'),
        ]
        return my_urls + urls

    def download_pdf_link(self, obj):
        url = reverse('admin:shop_invoice_download', args=[obj.pk])
        return format_html('<a class="button" href="{}">Download PDF</a>', url)
    download_pdf_link.short_description = 'Invoice PDF'

    def download_pdf(self, request, invoice_id):
        invoice = get_object_or_404(Invoice, pk=invoice_id)
        from shop.invoicing import render_invoice_pdf
        payload = render_invoice_pdf(invoice)
        response = HttpResponse(payload, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="invoice_{invoice.invoice_number}.pdf"'
        response['Cache-Control'] = 'no-store'
        return response

    def download_selected_pdfs(self, request, queryset):
        if not queryset.exists():
            self.message_user(request, 'No invoices selected.', level='error')
            return
        from shop.invoicing import render_invoice_pdf
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            for invoice in queryset:
                try:
                    zf.writestr(f"invoice_{invoice.invoice_number}.pdf", render_invoice_pdf(invoice))
                except Exception:
                    continue
        buffer.seek(0)
        response = HttpResponse(buffer.read(), content_type='application/zip')
        response['Content-Disposition'] = 'attachment; filename="invoices.zip"'
        return response
    download_selected_pdfs.short_description = 'Download selected invoices (ZIP)'


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('user', 'notification_type', 'title', 'is_read', 'created_at')
    list_filter = ('notification_type', 'is_read', 'created_at')
    search_fields = ('user__username', 'user__email', 'title', 'message')
    readonly_fields = ('created_at',)
    ordering = ('-created_at',)


def _admin_chart_context():
    """Revenue analytics context used by the Jazzmin admin index charts."""
    six_months_ago = timezone.now() - timedelta(days=6 * 30)
    revenue_by_month = {}
    for period in range(5, -1, -1):
        d = timezone.now() - timedelta(days=period * 30)
        revenue_by_month[d.strftime('%b')] = 0
    rows = (
        Order.objects.exclude(status='Cancelled')
        .filter(created_at__gte=six_months_ago)
        .annotate(month=TruncMonth('created_at'))
        .values('month')
        .annotate(total=Sum('total_amount'))
    )
    for row in rows:
        revenue_by_month[row['month'].strftime('%b')] = round(row['total'] or 0)
    revenue_month_labels = list(revenue_by_month.keys())
    revenue_month_values = list(revenue_by_month.values())

    local_now = timezone.localtime()
    today_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    hour_rows = (
        Order.objects.exclude(status='Cancelled')
        .filter(created_at__gte=today_start)
        .annotate(hour=TruncHour('created_at'))
        .values('hour')
        .annotate(total=Sum('total_amount'), count=Count('id'))
    )
    hourly_revenue = {h: 0 for h in range(24)}
    hourly_count = {h: 0 for h in range(24)}
    for row in hour_rows:
        h = timezone.localtime(row['hour']).hour
        hourly_revenue[h] = round(row['total'] or 0)
        hourly_count[h] = row['count']

    return {
        'revenue_month_labels': json.dumps(revenue_month_labels),
        'revenue_month_values': json.dumps(revenue_month_values),
        'hour_labels': json.dumps([f"{h:02d}:00" for h in range(24)]),
        'hour_revenue_values': json.dumps([hourly_revenue[h] for h in range(24)]),
        'hour_count_values': json.dumps([hourly_count[h] for h in range(24)]),
        'today_label': timezone.localtime().strftime('%d %b %Y'),
    }


_original_admin_index = admin.site.index


def _admin_index_with_charts(request, extra_context=None):
    context = dict(extra_context or {})
    context.update(_admin_chart_context())
    return _original_admin_index(request, extra_context=context)


admin.site.index = _admin_index_with_charts