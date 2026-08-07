"""Notification helpers for KaviBazaar.

Every event that should surface in the user's notification bell goes through
this module. `notify()` is the single entry point; convenience wrappers keep
call sites readable.
"""

from django.contrib.auth.models import User

from .models import Notification, NOTIFICATION_ICONS, Cart


def notify(user, notification_type, title, message='', icon='', link=''):
    """Create one notification for a single user."""
    if not user or not user.is_authenticated:
        return None
    if not icon:
        icon = NOTIFICATION_ICONS.get(notification_type, 'fa-bell')
    return Notification.objects.create(
        user=user,
        notification_type=notification_type,
        icon=icon,
        title=title[:255],
        message=message,
        link=link or '',
    )


def notify_many(users, notification_type, title, message='', icon='', link=''):
    """Create one notification per user (used for broadcasts)."""
    created = 0
    for user in users:
        if user and user.is_authenticated:
            notify(user, notification_type, title, message, icon, link)
            created += 1
    return created


def _order_product_names(order, user):
    """Product names for an order.

    OrderItems are created after the order-placed notification fires during
    online checkout, so fall back to the user's cart (still populated at that
    point). Returns a formatted list string, e.g. "Wireless Earbuds, Smart
    Watch +2 more" or '' when nothing is available.
    """
    names = list(order.items.select_related('product').values_list('product__name', flat=True))
    if not names and user:
        names = list(Cart.objects.filter(user=user).values_list('product__name', flat=True))
    names = [n for n in names if n]
    if not names:
        return ''
    if len(names) <= 3:
        return ', '.join(names)
    return f"{', '.join(names[:3])} +{len(names) - 3} more"


def notify_order_placed(user, order):
    names = _order_product_names(order, user)
    if names:
        message = f"Your order for {names} has been placed successfully."
    else:
        message = "Your order has been placed successfully."
    notify(
        user, 'order_placed', "Order Placed Successfully",
        message,
        link='/my_orders',
    )


def notify_payment_success(user, order):
    notify(
        user, 'payment_success', "Payment Successful",
        f"We have received your payment of Rs. {order.total_amount:g}. Thank you!",
        link='/my_orders',
    )


def notify_payment_failed(user, order):
    notify(
        user, 'payment_failed', "Payment Failed",
        f"We could not process your payment of Rs. {order.total_amount:g}. Please try again.",
        link='/my_orders',
    )


def notify_order_confirmed(user, order):
    notify(
        user, 'order_confirmed', "Order Confirmed",
        "Your order has been confirmed and is being processed.",
        link='/my_orders',
    )


def notify_order_shipped(user, order):
    notify(
        user, 'order_shipped', "Order Shipped",
        "Great news! Your order is on its way. Track it from My Orders.",
        link='/my_orders',
    )


def notify_out_for_delivery(user, order):
    notify(
        user, 'out_for_delivery', "Out for Delivery",
        "Your order is out for delivery and should reach you today.",
        link='/my_orders',
    )


def notify_order_delivered(user, order):
    notify(
        user, 'order_delivered', "Order Delivered",
        "Your order has been delivered. We hope you love it!",
        link='/my_orders',
    )


def notify_order_cancelled(user, order, reason=''):
    msg = "Your order has been cancelled."
    if reason:
        msg += f" Reason: {reason}"
    notify(
        user, 'order_cancelled', "Order Cancelled", msg,
        link='/my_orders',
    )


def notify_order_refunded(user, order):
    notify(
        user, 'order_refunded', "Refund Initiated",
        "Your refund has been initiated. It will reflect in 5-7 business days.",
        link='/my_orders',
    )


def notify_refund_completed(user, order):
    notify(
        user, 'refund_completed', "Refund Completed",
        "Your refund has been completed successfully.",
        link='/my_orders',
    )


def notify_return_approved(user, order):
    notify(
        user, 'return_approved', "Return Request Approved",
        "Your return request has been approved. A pickup will be arranged shortly.",
        link='/my_orders',
    )


def notify_return_rejected(user, order):
    notify(
        user, 'return_rejected', "Return Request Rejected",
        "We regret to inform you that your return request was not approved.",
        link='/my_orders',
    )


def notify_wishlist_back_in_stock(user, product):
    notify(
        user, 'wishlist_back_in_stock', f"{product.name} is back in stock",
        "A product in your wishlist is back in stock. Grab it before it goes away!",
        link=f'/collections/{product.category.name}/{product.name}',
    )


def notify_cart_back_in_stock(user, product):
    notify(
        user, 'back_in_stock', f"{product.name} is back in stock",
        "A product in your cart is back in stock. Complete your order now!",
        link='/cart',
    )


def notify_price_drop(user, product, old_price, new_price):
    notify(
        user, 'price_drop', f"Price drop on {product.name}",
        f"Price dropped from Rs. {old_price:g} to Rs. {new_price:g}. Save Rs. {old_price - new_price:g}!",
        link=f'/collections/{product.category.name}/{product.name}',
    )


def notify_login_new_device(user):
    notify(
        user, 'login_new_device', "New login on your account",
        "You just logged in to your KaviBazaar account. If this wasn't you, change your password immediately.",
    )


def notify_password_changed(user):
    notify(
        user, 'password_changed', "Password changed successfully",
        "Your account password was changed successfully.",
    )


def notify_email_verified(user):
    notify(
        user, 'email_verified', "Email verified",
        "Your email address has been verified successfully.",
    )


def notify_announcement(user, title, message=''):
    notify(user, 'announcement', title, message, link='/')


def notify_product_back_in_stock(product):
    """Broadcast back-in-stock to users who wishlisted or carted the product."""
    from .models import Favourite, Cart
    fav_users = User.objects.filter(favourite__product=product).distinct()
    cart_users = User.objects.filter(cart__product=product).distinct()
    for user in fav_users:
        notify_wishlist_back_in_stock(user, product)
    for user in cart_users.exclude(pk__in=fav_users.values_list('pk', flat=True)):
        notify_cart_back_in_stock(user, product)


def notify_product_price_drop(product, old_price, new_price):
    """Broadcast a price drop to all users who wishlisted the product."""
    from .models import Favourite
    if new_price >= old_price:
        return
    users = User.objects.filter(favourite__product=product).distinct()
    for user in users:
        notify_price_drop(user, product, old_price, new_price)
