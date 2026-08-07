from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import datetime
import os
import re


def getFileName(request, filename):
    now_time = datetime.datetime.now().strftime("%Y%m%d%H:%M:%S")
    new_filename = "%s%s" % (now_time, filename)
    return os.path.join('uploads/', new_filename)


def add_business_days(start, days):
    result = start
    added = 0
    while added < days:
        result += datetime.timedelta(days=1)
        if result.weekday() < 5:
            added += 1
    return result


STORE_PINCODE = '600001'


def normalize_pincode(value):
    if not value:
        return ''
    return ''.join(ch for ch in str(value) if ch.isdigit())[:6]


def extract_pincode(text):
    if not text:
        return ''
    match = re.search(r'\b[1-9]\d{5}\b', str(text))
    return match.group(0) if match else ''


def estimate_delivery_days(pincode):
    pin = normalize_pincode(pincode)
    if len(pin) == 6:
        if pin[:3] == STORE_PINCODE[:3]:
            return 2
        if pin[:2] == STORE_PINCODE[:2]:
            return 3
        return 5
    return 4


class Catagory(models.Model):
    name = models.CharField(max_length=150, null=False, blank=False)
    image = models.ImageField(upload_to=getFileName, null=True, blank=True)
    description = models.TextField(max_length=500, null=False, blank=False)
    status = models.BooleanField(default=False, help_text="0-show,1-Hidden")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Product(models.Model):
    category = models.ForeignKey(Catagory, on_delete=models.CASCADE)
    name = models.CharField(max_length=150, null=False, blank=False)
    vendor = models.CharField(max_length=150, null=False, blank=False)
    product_image = models.ImageField(upload_to=getFileName, null=True, blank=True)
    quantity = models.IntegerField(null=False, blank=False)
    original_price = models.FloatField(null=False, blank=False)
    selling_price = models.FloatField(null=False, blank=False)
    description = models.TextField(max_length=500, null=False, blank=False)
    status = models.BooleanField(default=False, help_text="0-show,1-Hidden")
    trending = models.BooleanField(default=False, help_text="0-default,1-Trending")
    cash_on_delivery = models.BooleanField(default=False, help_text="Cash on Delivery available for this product")
    created_at = models.DateTimeField(auto_now_add=True)
    highlight_1 = models.CharField(max_length=255, blank=True, default='100% Genuine product from Flipkart')
    highlight_2 = models.CharField(max_length=255, blank=True, default='7-day replacement guarantee')
    highlight_3 = models.CharField(max_length=255, blank=True, default='Secure payment & on-time delivery')
    perk_1_icon = models.CharField(max_length=50, blank=True, default='fa-truck')
    perk_1_title = models.CharField(max_length=100, blank=True, default='Free delivery')
    perk_1_sub = models.CharField(max_length=100, blank=True, default='2–4 business days')
    perk_2_icon = models.CharField(max_length=50, blank=True, default='fa-rotate-left')
    perk_2_title = models.CharField(max_length=100, blank=True, default='7-day returns')
    perk_2_sub = models.CharField(max_length=100, blank=True, default='Hassle-free')
    perk_3_icon = models.CharField(max_length=50, blank=True, default='fa-shield')
    perk_3_title = models.CharField(max_length=100, blank=True, default='Secure payment')
    perk_3_sub = models.CharField(max_length=100, blank=True, default='100% protected')

    def __str__(self):
        return self.name

    @property
    def discount_percent(self):
        if self.original_price and self.original_price > 0:
            return int((1 - self.selling_price / self.original_price) * 100)
        return 0


class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to=getFileName, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.product.name} image"


class Cart(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    product_qty = models.IntegerField(null=False, blank=False)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def total_cost(self):
        return self.product_qty * self.product.selling_price


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    mobile_number = models.CharField(max_length=15, unique=True, null=True, blank=True)
    profile_picture = models.ImageField(upload_to=getFileName, null=True, blank=True)
    dashboard_access = models.BooleanField(default=True, verbose_name='Dashboard access')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.mobile_number or 'no mobile'}"


class Favourite(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)


# ── Order Models ──

ORDER_STATUS = (
    ('Pending', 'Pending'),
    ('Processing', 'Processing'),
    ('Shipped', 'Shipped'),
    ('Delivered', 'Delivered'),
    ('Cancelled', 'Cancelled'),
)


class Order(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    total_amount = models.FloatField(null=False, blank=False)
    status = models.CharField(max_length=50, choices=ORDER_STATUS, default='Pending')
    address = models.TextField(max_length=500, null=False, blank=False)
    pincode = models.CharField(max_length=10, blank=True, null=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    phone = models.CharField(max_length=15, null=False, blank=False)
    alternate_phone = models.CharField(max_length=15, null=True, blank=True)
    razorpay_order_id = models.CharField(max_length=100, null=True, blank=True)
    razorpay_pay_id = models.CharField(max_length=100, null=True, blank=True)
    razorpay_signature = models.CharField(max_length=200, null=True, blank=True)
    payment_status = models.CharField(max_length=20, default='Pending')
    cancel_reason = models.TextField(blank=True, null=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True, help_text="When the order was marked Delivered")
    expected_delivery_date = models.DateField(null=True, blank=True, help_text="Estimated delivery date shown to the customer")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if self.status == 'Delivered':
            if not self.delivered_at:
                self.delivered_at = timezone.now()
        else:
            self.delivered_at = None
        if not self.expected_delivery_date:
            days = estimate_delivery_days(self.pincode or extract_pincode(self.address))
            self.expected_delivery_date = add_business_days(self.created_at or timezone.now(), days).date()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Order #{self.id} by {self.user.username}"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.IntegerField(null=True, blank=True)
    price = models.FloatField(null=True, blank=True)

    def __str__(self):
        if self.product:
            return f"{self.product.name} x {self.quantity}"
        return "Order Item"

    @property
    def total_cost(self):
        if self.quantity and self.price:
            return self.quantity * self.price
        return 0


# ── Payment Model ──

PAYMENT_STATUS = (
    ('PENDING', 'PENDING'),
    ('SUCCESS', 'SUCCESS'),
    ('FAILED', 'FAILED'),
    ('CANCELLED', 'CANCELLED'),
)


class Payment(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    order = models.ForeignKey(Order, on_delete=models.SET_NULL, null=True, blank=True, related_name='payments')
    amount = models.FloatField(null=False, blank=False)
    payment_gateway = models.CharField(max_length=50, default='RAZORPAY')
    razorpay_order_id = models.CharField(max_length=100, null=True, blank=True)
    razorpay_pay_id = models.CharField(max_length=100, null=True, blank=True)
    razorpay_signature = models.CharField(max_length=200, null=True, blank=True)
    status = models.CharField(max_length=20, choices=PAYMENT_STATUS, default='PENDING')
    gateway_response = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Payment #{self.id} - {self.status}"

    @property
    def is_success(self):
        return self.status == 'SUCCESS'


class SavedAddress(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='saved_addresses')
    label = models.CharField(max_length=100, null=True, blank=True, help_text="e.g. Home, Office")
    address = models.TextField(max_length=500, null=False, blank=False)
    locality = models.CharField(max_length=200, null=True, blank=True)
    landmark = models.CharField(max_length=200, null=True, blank=True)
    pincode = models.CharField(max_length=10, null=True, blank=True)
    phone = models.CharField(max_length=15, null=True, blank=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.label or 'Address'} - {self.address}, {self.locality or ''} - {self.pincode or ''}"


class LoginOTP(models.Model):
    identifier = models.CharField(max_length=150, db_index=True)
    otp_hash = models.CharField(max_length=255)
    is_used = models.BooleanField(default=False)
    attempts = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Login OTP for {self.identifier} (used={self.is_used})"

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at


class ProductRating(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='ratings')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='product_ratings')
    order_item = models.ForeignKey('OrderItem', on_delete=models.CASCADE, related_name='ratings', null=True, blank=True)
    rating = models.PositiveSmallIntegerField(default=5, help_text="1-5 stars")
    comment = models.TextField(blank=True, default='')
    image = models.ImageField(upload_to='ratings/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('product', 'user', 'order_item')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} rated {self.product.name} {self.rating}/5"


class ProductRatingMedia(models.Model):
    MEDIA_TYPES = [
        ('image', 'Image'),
        ('video', 'Video'),
    ]
    rating = models.ForeignKey(ProductRating, on_delete=models.CASCADE, related_name='media')
    file = models.FileField(upload_to='ratings/', blank=True, null=True)
    media_type = models.CharField(max_length=10, choices=MEDIA_TYPES, default='image')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.media_type} for rating {self.rating_id}"


# ── Notifications ──

NOTIFICATION_TYPES = (
    ('order_placed', 'Order Placed'),
    ('payment_success', 'Payment Successful'),
    ('payment_failed', 'Payment Failed'),
    ('order_confirmed', 'Order Confirmed'),
    ('order_shipped', 'Order Shipped'),
    ('out_for_delivery', 'Out for Delivery'),
    ('order_delivered', 'Order Delivered'),
    ('order_cancelled', 'Order Cancelled'),
    ('order_refunded', 'Order Refunded'),
    ('refund_completed', 'Refund Completed'),
    ('return_approved', 'Return Request Approved'),
    ('return_rejected', 'Return Request Rejected'),
    ('back_in_stock', 'Back in Stock'),
    ('wishlist_back_in_stock', 'Wishlist Item Back in Stock'),
    ('price_drop', 'Price Drop'),
    ('login_new_device', 'New Device Login'),
    ('password_changed', 'Password Changed'),
    ('email_verified', 'Email Verified'),
    ('announcement', 'Admin Announcement'),
)

NOTIFICATION_ICONS = {
    'order_placed': 'fa-shopping-bag',
    'payment_success': 'fa-check-circle',
    'payment_failed': 'fa-times-circle',
    'order_confirmed': 'fa-check',
    'order_shipped': 'fa-truck',
    'out_for_delivery': 'fa-truck',
    'order_delivered': 'fa-home',
    'order_cancelled': 'fa-ban',
    'order_refunded': 'fa-undo',
    'refund_completed': 'fa-money',
    'return_approved': 'fa-arrow-circle-left',
    'return_rejected': 'fa-arrow-circle-left',
    'back_in_stock': 'fa-cube',
    'wishlist_back_in_stock': 'fa-heart',
    'price_drop': 'fa-inr',
    'login_new_device': 'fa-shield',
    'password_changed': 'fa-lock',
    'email_verified': 'fa-envelope-open',
    'announcement': 'fa-bullhorn',
}


class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    notification_type = models.CharField(max_length=50, choices=NOTIFICATION_TYPES)
    icon = models.CharField(max_length=50, blank=True, default='fa-bell')
    title = models.CharField(max_length=255)
    message = models.TextField(blank=True, default='')
    link = models.CharField(max_length=500, blank=True, default='', help_text="Optional URL opened when the notification is clicked")
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']

    def __str__(self):
        return f"[{self.notification_type}] {self.title} -> {self.user.username} (read={self.is_read})"


# ── Invoice (PDF) ──

class Invoice(models.Model):
    """Snapshot of a successful order for PDF invoice generation.

    Generated automatically when an order becomes successful so the invoice
    always reflects the exact details at the time of purchase, even if
    product prices change later.
    """
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name='invoice')
    invoice_number = models.CharField(max_length=30, unique=True, editable=False)
    issued_date = models.DateTimeField(auto_now_add=True)

    customer_name = models.CharField(max_length=255)
    customer_email = models.EmailField(blank=True, default='')
    customer_phone = models.CharField(max_length=20, blank=True, default='')
    delivery_address = models.TextField(blank=True, default='')

    order_date = models.DateTimeField()
    payment_method = models.CharField(max_length=50, blank=True, default='')
    payment_status = models.CharField(max_length=50, blank=True, default='')
    order_status = models.CharField(max_length=50, blank=True, default='')

    subtotal = models.FloatField(default=0.0, help_text="Sum of MRP totals")
    total_discount = models.FloatField(default=0.0, help_text="Total savings vs MRP")
    delivery_charge = models.FloatField(default=0.0)
    tax_amount = models.FloatField(default=0.0)
    grand_total = models.FloatField(default=0.0)

    line_items = models.JSONField(default=list, help_text="Snapshot of products, qty, prices and images at purchase time")

    class Meta:
        ordering = ['-issued_date']

    def __str__(self):
        return self.invoice_number