from .models import Cart, UserProfile, Notification


def has_dashboard_access(user):
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    if not user.is_staff:
        return False
    profile = UserProfile.objects.filter(user=user).first()
    return bool(profile and profile.dashboard_access)


_ADMIN_NAV_PERMS = frozenset((
    'shop.view_product',
    'shop.view_catagory',
    'shop.view_order',
    'shop.view_payment',
    'shop.view_productrating',
    'shop.change_product',
    'shop.change_notification',
))


def has_admin_access(user):
    """True when the user can use the KaviBazaar admin at all (dashboard or any
    granted navigation section). Keeps staff users out of the /dashboard/ ->
    home redirect loop when they have no navigation sections selected."""
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    if not user.is_staff:
        return False
    if has_dashboard_access(user):
        return True
    return bool(user.get_all_permissions() & _ADMIN_NAV_PERMS)


def cart_count(request):
    count = 0
    if request.user.is_authenticated:
        count = Cart.objects.filter(user=request.user).count()
    return {'cart_count': count}


def profile_picture(request):
    url = ''
    if request.user.is_authenticated:
        profile = UserProfile.objects.filter(user=request.user).first()
        if profile and profile.profile_picture:
            url = profile.profile_picture.url
    return {'profile_picture': url}


def dashboard_access(request):
    return {'dashboard_access': has_dashboard_access(request.user)}


def unread_notifications_count(request):
    count = 0
    if request.user.is_authenticated:
        count = Notification.objects.filter(user=request.user, is_read=False).count()
    return {'unread_notifications_count': count}


def search_scope(request):
    from urllib.parse import unquote
    scope = 'products'
    category = ''
    path = request.path.strip('/')
    parts = [unquote(p) for p in path.split('/')] if path else []

    if parts and parts[0] == 'collections':
        if len(parts) == 1:
            scope = 'categories'
        else:
            scope = 'category_products'
            category = parts[1]
    elif parts and parts[0] == 'cart':
        scope = 'cart'
    elif parts and parts[0] in ('favviewpage', 'fav'):
        scope = 'favourites'
    elif parts and parts[0] == 'my_orders':
        scope = 'orders'

    # Refining search from a scoped results page keeps the same scope
    if parts and parts[0] == 'search':
        qs_scope = request.GET.get('scope', '')
        if qs_scope in ('categories', 'category_products', 'cart', 'favourites', 'orders'):
            scope = qs_scope
            category = request.GET.get('category', category)

    return {
        'search_scope': scope,
        'search_category': category,
        'current_category': category,
    }
