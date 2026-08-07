import json
import logging
import re
import secrets
import urllib.request
import urllib.parse
from datetime import timedelta
import calendar
import razorpay

import datetime
from functools import wraps
from django.db import models
from django.db.models import Sum, Count, Avg
from django.db.models.functions import TruncMonth, TruncHour
from django.http import JsonResponse, HttpResponse, Http404
from django.shortcuts import redirect, render, get_object_or_404
from django.template.loader import render_to_string
from django.urls import reverse
from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.views.decorators.csrf import csrf_exempt

from shop.services import send_otp_email
from shop.utils import optimize_image, delete_image_file, collect_product_images, fetch_gravatar, fetch_google_picture
from shop.notifications import (
    notify_many,
    notify_order_placed,
    notify_payment_success,
    notify_payment_failed,
    notify_order_confirmed,
    notify_order_shipped,
    notify_order_delivered,
    notify_order_cancelled,
    notify_login_new_device,
    notify_product_back_in_stock,
    notify_product_price_drop,
)
from .context_processors import has_admin_access, has_dashboard_access
from .invoicing import generate_invoice_for_order
from .smart_search import (
    SORT_MAP,
    build_chips,
    parse_query,
    related_products,
    smart_search,
)
from .models import *
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.models import User, Permission
from django.contrib.auth.hashers import make_password, check_password
from django.core.mail import send_mail
from django.utils import timezone

logger = logging.getLogger(__name__)


def staff_perm(perm, login_url='/login'):
    """Require an authenticated staff/superuser with the given Django permission."""
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect(login_url)
            if not (request.user.is_staff or request.user.is_superuser):
                return redirect('/')
            if not request.user.has_perm(perm):
                messages.error(request, "You don't have permission to access that page.")
                return redirect('admin_dashboard')
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator


def home(request):
    if request.user.is_authenticated and request.user.is_staff and has_admin_access(request.user):
        return redirect('admin_dashboard')
    products = Product.objects.filter(status=0).annotate(
        avg_rating=Avg('ratings__rating'),
        rating_count=Count('ratings'),
    ).order_by('-created_at', '-id')[:40]
    categories = Catagory.objects.filter(status=0).order_by('created_at', 'id')
    return render(request, 'shop/index.html', {'products': products, 'categories': categories})


@staff_perm('shop.change_product')
def low_stock(request):
    if request.method == 'POST':
        product = get_object_or_404(Product, id=request.POST.get('product_id'))
        try:
            quantity = int(request.POST.get('quantity'))
            if quantity < 0:
                raise ValueError
            old_qty = product.quantity
            product.quantity = quantity
            product.save(update_fields=['quantity'])
            if old_qty <= 0 and quantity > 0:
                notify_product_back_in_stock(product)
            messages.success(request, f"'{product.name}' stock updated to {quantity}.")
        except (ValueError, TypeError):
            messages.error(request, f"Invalid quantity for '{product.name}'.")
        return redirect('low_stock')
    products = Product.objects.filter(quantity__lte=5).select_related('category').order_by('quantity', 'id')
    return render(request, 'shop/admin/low_stock.html', {'products': products})


def search_autocomplete(request):
    q = request.GET.get('q', '').strip()
    scope = request.GET.get('scope', 'products')
    category = request.GET.get('category', '')
    if not q:
        return JsonResponse([], safe=False)

    if scope == 'categories':
        items = [
            {
                'type': 'category',
                'name': c.name,
                'price': f"{c.product_set.count()} items",
                'image': c.image.url if c.image else '',
                'url': reverse('collections', args=[c.name]),
            }
            for c in Catagory.objects.filter(status=0, name__icontains=q)[:8]
        ]
    elif scope == 'category_products':
        products = Product.objects.filter(
            status=0, category__name=category
        ).filter(
            models.Q(name__icontains=q) | models.Q(vendor__icontains=q)
        )[:8]
        items = [{
            'type': 'product',
            'name': p.name,
            'image': p.product_image.url if p.product_image else '',
            'price': 'Rs.' + str(int(p.selling_price)),
            'url': reverse('product_details', args=[p.category.name, p.name]),
        } for p in products]
    elif scope == 'cart':
        carts = Cart.objects.none()
        if request.user.is_authenticated:
            carts = Cart.objects.filter(
                user=request.user, product__name__icontains=q
            ).select_related('product')[:8]
        items = [{
            'type': 'product',
            'name': c.product.name,
            'image': c.product.product_image.url if c.product.product_image else '',
            'price': 'Qty ' + str(c.product_qty),
            'url': reverse('cart') + '#cart-' + str(c.id),
        } for c in carts]
    elif scope == 'favourites':
        favs = Favourite.objects.none()
        if request.user.is_authenticated:
            favs = Favourite.objects.filter(
                user=request.user, product__name__icontains=q
            ).select_related('product')[:8]
        items = [{
            'type': 'product',
            'name': f.product.name,
            'image': f.product.product_image.url if f.product.product_image else '',
            'price': 'Rs.' + str(int(f.product.selling_price)),
            'url': reverse('favviewpage') + '#fav-' + str(f.id),
        } for f in favs]
    elif scope == 'orders':
        orders = Order.objects.none()
        if request.user.is_authenticated:
            orders = Order.objects.filter(user=request.user).filter(
                models.Q(id__icontains=q) | models.Q(items__product__name__icontains=q)
            ).distinct().order_by('-created_at')[:8]
        items = [{
            'type': 'order',
            'name': 'Order',
            'price': o.status,
            'image': '',
            'url': reverse('my_orders') + '#order-' + str(o.id),
        } for o in orders]
    else:
        products = Product.objects.filter(status=0).filter(
            models.Q(name__icontains=q) |
            models.Q(category__name__icontains=q) |
            models.Q(vendor__icontains=q)
        )[:8]
        items = [{
            'type': 'product',
            'name': p.name,
            'image': p.product_image.url if p.product_image else '',
            'price': 'Rs.' + str(int(p.selling_price)),
            'url': reverse('product_details', args=[p.category.name, p.name]),
        } for p in products]
        if not items and len(q.split()) >= 2:
            smart_items, _ = smart_search(q, rank_limit=40)
            for p in smart_items[:8]:
                items.append({
                    'type': 'product',
                    'name': p.name,
                    'image': p.product_image.url if p.product_image else '',
                    'price': 'Rs.' + str(int(p.selling_price)),
                    'url': reverse('product_details', args=[p.category.name, p.name]),
                })
    return JsonResponse(items, safe=False)


def search(request):
    query = request.GET.get('q', '').strip()
    scope = request.GET.get('scope', 'products')
    category = request.GET.get('category', '')
    sort_by = request.GET.get('sort', '')
    min_price = request.GET.get('min_price', '')
    max_price = request.GET.get('max_price', '')

    allowed_scopes = ('products', 'categories', 'category_products', 'cart', 'favourites', 'orders')
    if scope not in allowed_scopes:
        scope = 'products'

    products = None
    parsed = None
    chips = []
    related = None
    products_count = 0
    if scope in ('products', 'category_products'):
        if query:
            products, parsed = smart_search(
                query,
                scope_category=category if scope == 'category_products' else None,
                sort_by=sort_by,
                min_price=min_price,
                max_price=max_price,
            )
            chips = build_chips(parsed) if parsed else []
            products_count = len(products) if isinstance(products, list) else products.count()
            if products_count == 0:
                related = related_products(parsed or parse_query(query))
        else:
            products = Product.objects.filter(status=0).annotate(
                avg_rating=Avg('ratings__rating'),
                rating_count=Count('ratings'),
            )
            if scope == 'category_products' and category:
                products = products.filter(category__name=category)
            if min_price:
                products = products.filter(selling_price__gte=float(min_price))
            if max_price:
                products = products.filter(selling_price__lte=float(max_price))
            if sort_by in SORT_MAP:
                products = products.order_by(SORT_MAP[sort_by])
            if not query and not category:
                products = products.none()
            products_count = products.count()

    elif scope == 'categories':
        if query:
            products = Catagory.objects.filter(status=0, name__icontains=query).order_by('name')
        else:
            products = Catagory.objects.none()

    elif scope == 'cart':
        products = Cart.objects.none()
        if request.user.is_authenticated:
            products = Cart.objects.filter(user=request.user).select_related('product').order_by('-created_at').annotate(
                avg_rating=Avg('product__ratings__rating'),
                rating_count=Count('product__ratings'),
            )
            if query:
                products = products.filter(product__name__icontains=query)

    elif scope == 'favourites':
        products = Favourite.objects.none()
        if request.user.is_authenticated:
            products = Favourite.objects.filter(user=request.user).select_related('product').order_by('-created_at').annotate(
                avg_rating=Avg('product__ratings__rating'),
                rating_count=Count('product__ratings'),
            )
            if query:
                products = products.filter(product__name__icontains=query)

    elif scope == 'orders':
        products = Order.objects.none()
        if request.user.is_authenticated:
            products = Order.objects.filter(user=request.user).order_by('-created_at')
            if query:
                products = products.filter(
                    models.Q(id__icontains=query) | models.Q(items__product__name__icontains=query)
                ).distinct()

    categories = Catagory.objects.filter(status=0)

    return render(request, 'shop/search.html', {
        'products': products,
        'query': query,
        'scope': scope,
        'categories': categories,
        'selected_category': category,
        'sort_by': sort_by,
        'min_price': min_price,
        'max_price': max_price,
        'chips': chips,
        'related': related,
        'products_count': products_count,
    })


def favviewpage(request):
    if request.user.is_authenticated:
        fav = Favourite.objects.filter(user=request.user).annotate(
            avg_rating=Avg('product__ratings__rating'),
            rating_count=Count('product__ratings'),
        )
        return render(request, "shop/fav.html", {"fav": fav})
    else:
        return redirect("/login")


def remove_fav(request, fid):
    item = Favourite.objects.get(id=fid)
    item.delete()
    return redirect("/favviewpage")


def cart_page(request):
    if request.user.is_authenticated:
        cart = Cart.objects.filter(user=request.user)
        return render(request, "shop/cart.html", {"cart": cart})
    else:
        return redirect("/login")


def remove_cart(request, cid):
    cartitem = Cart.objects.get(id=cid)
    cartitem.delete()
    return redirect("/cart")


def fav_page(request):
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        if request.user.is_authenticated:
            data = json.load(request)
            product_id = data['pid']
            product_status = Product.objects.get(id=product_id)
            if product_status:
                existing = Favourite.objects.filter(user=request.user.id, product_id=product_id)
                if existing:
                    existing.delete()
                    return JsonResponse({'status': 'Product Removed from Favourite'}, status=200)
                else:
                    Favourite.objects.create(user=request.user, product_id=product_id)
                    return JsonResponse({'status': 'Product Added to Favourite'}, status=200)
        else:
            return JsonResponse({'status': 'Login to Add Favourite'}, status=200)
    else:
        return JsonResponse({'status': 'Invalid Access'}, status=200)


def add_to_cart(request):
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        if request.user.is_authenticated:
            data = json.load(request)
            product_qty = data['product_qty']
            product_id = data['pid']
            product_status = Product.objects.get(id=product_id)
            if product_status:
                if Cart.objects.filter(user=request.user.id, product_id=product_id):
                    return JsonResponse({'status': 'Product Already in Cart'}, status=200)
                else:
                    if product_status.quantity >= product_qty:
                        Cart.objects.create(user=request.user, product_id=product_id, product_qty=product_qty)
                        return JsonResponse({'status': 'Product Added to Cart'}, status=200)
                    else:
                        return JsonResponse({'status': 'Product Stock Not Available'}, status=200)
        else:
            return JsonResponse({'status': 'redirect', 'url': '/login'}, status=200)
    else:
        return JsonResponse({'status': 'Invalid Access'}, status=200)


# ── Place Order (Show checkout page) ──
def save_address_from_post(request):
    """Create a SavedAddress from POST data when 'save_address' is checked."""
    if request.POST.get('save_address') not in ('on', 'true', '1'):
        return None
    address = request.POST.get('address', '').strip()
    pincode = request.POST.get('pincode', '').strip()
    if not address or not pincode:
        return None
    label = request.POST.get('address_label', '').strip()
    if not label:
        label = f"Address {request.user.saved_addresses.count() + 1}"
    lat_str = request.POST.get('latitude', '').strip()
    lng_str = request.POST.get('longitude', '').strip()
    return SavedAddress.objects.create(
        user=request.user,
        label=label,
        address=address,
        locality=request.POST.get('locality', '').strip(),
        landmark=request.POST.get('landmark', '').strip(),
        pincode=pincode,
        phone=request.POST.get('phone', '').strip(),
        latitude=float(lat_str) if lat_str else None,
        longitude=float(lng_str) if lng_str else None,
    )


def place_order(request):
    if not request.user.is_authenticated:
        return redirect("/login")

    cart_items = Cart.objects.filter(user=request.user)
    if not cart_items.exists():
        messages.warning(request, "Your cart is empty!")
        return redirect("/cart")

    total = sum(item.total_cost for item in cart_items)
    mrp = sum((item.product.original_price or 0) * item.product_qty for item in cart_items)
    discount = max(0, mrp - total)
    buy_now_pid = request.GET.get('buy_now', '').strip()
    if buy_now_pid:
        buy_now_items = cart_items.filter(product_id=buy_now_pid)
        cod_available = all(item.product.cash_on_delivery for item in buy_now_items) if buy_now_items.exists() else False
    else:
        cod_available = all(item.product.cash_on_delivery for item in cart_items)
    saved_addresses = SavedAddress.objects.filter(user=request.user)
    saved_addresses_json = [{
        'id': a.id,
        'label': a.label or 'Address',
        'address': a.address,
        'locality': a.locality or '',
        'landmark': a.landmark or '',
        'pincode': a.pincode or '',
        'phone': a.phone or '',
        'latitude': a.latitude,
        'longitude': a.longitude,
    } for a in saved_addresses]
    return render(request, 'shop/place_order.html', {
        'cart': cart_items,
        'total': total,
        'mrp': mrp,
        'discount': discount,
        'razorpay_key_id': settings.RAZORPAY_KEY_ID,
        'google_maps_api_key': settings.GOOGLE_MAPS_API_KEY,
        'razorpay_configured': is_razorpay_configured(),
        'cod_available': cod_available,
        'buy_now_pid': buy_now_pid,
        'saved_addresses': saved_addresses,
        'saved_addresses_json': saved_addresses_json,
    })


# ── Create Order (AJAX) ──
def create_order(request):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Login required'}, status=401)

    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request'}, status=400)

    cart_items = Cart.objects.filter(user=request.user)
    if not cart_items.exists():
        return JsonResponse({'error': 'Cart is empty'}, status=400)

    address = request.POST.get('address', '').strip()
    phone = request.POST.get('phone', '').strip()
    latitude = request.POST.get('latitude', '').strip()
    longitude = request.POST.get('longitude', '').strip()
    if not address or not phone:
        return JsonResponse({'error': 'Address and phone are required'}, status=400)
    phone_digits = ''.join(ch for ch in phone if ch.isdigit())
    if len(phone_digits) != 10:
        return JsonResponse({'error': 'Enter a valid 10-digit phone number.'}, status=400)
    phone = phone_digits

    total = sum(item.total_cost for item in cart_items)

    lat = float(latitude) if latitude else None
    lng = float(longitude) if longitude else None

    order = Order.objects.create(
        user=request.user,
        total_amount=total,
        address=address,
        pincode=request.POST.get('pincode', '').strip() or extract_pincode(address),
        latitude=lat,
        longitude=lng,
        phone=phone,
        status='Processing',
        payment_status='Paid'
    )

    for item in cart_items:
        OrderItem.objects.create(
            order=order,
            product=item.product,
            quantity=item.product_qty,
            price=item.product.selling_price
        )

    cart_items.delete()

    save_address_from_post(request)

    notify_order_placed(request.user, order)
    notify_order_confirmed(request.user, order)

    generate_invoice_for_order(order)

    return JsonResponse({
        'status': 'success',
        'db_order_id': order.id,
    })


# ═══════════════════════════════════════════
# ── Payment Integration (Razorpay) ──
# ═══════════════════════════════════════════

def is_razorpay_configured():
    key = settings.RAZORPAY_KEY_ID
    secret = settings.RAZORPAY_KEY_SECRET
    return ('XXXXXXXX' not in key and 'XXXX' not in key
            and (key.startswith('rzp_test') or key.startswith('rzp_live'))
            and len(secret) > 10)


def get_razorpay_client():
    return razorpay.Client(auth=(
        settings.RAZORPAY_KEY_ID,
        settings.RAZORPAY_KEY_SECRET
    ))


def create_order_items_from_cart(order, user):
    """Create OrderItems from the user's cart and clear the cart.
    Called only after a payment succeeds so an order is placed only on success."""
    if order.items.exists():
        return
    cart_items = Cart.objects.filter(user=user)
    for item in cart_items:
        OrderItem.objects.create(
            order=order,
            product=item.product,
            quantity=item.product_qty,
            price=item.product.selling_price
        )
    cart_items.delete()


# ── Step 1: Create Payment Order (AJAX) ──
def create_payment_order(request):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Login required'}, status=401)
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request'}, status=400)

    cart_items = Cart.objects.filter(user=request.user)
    if not cart_items.exists():
        return JsonResponse({'error': 'Cart is empty'}, status=400)

    pincode = request.POST.get('pincode', '').strip()
    locality = request.POST.get('locality', '').strip()
    address = request.POST.get('address', '').strip()
    landmark = request.POST.get('landmark', '').strip()
    phone = request.POST.get('phone', '').strip()
    latitude = request.POST.get('latitude', '').strip()
    longitude = request.POST.get('longitude', '').strip()
    method = request.POST.get('method', 'UPI').strip().upper()

    if not pincode or not locality or not address or not phone:
        return JsonResponse({'error': 'Pincode, locality, address and phone are required'}, status=400)
    phone_digits = ''.join(ch for ch in phone if ch.isdigit())
    if len(phone_digits) != 10:
        return JsonResponse({'error': 'Enter a valid 10-digit phone number.'}, status=400)
    phone = phone_digits

    full_address = f"{address}, {locality}"
    if landmark:
        full_address += f", {landmark}"
    full_address += f" - {pincode}"

    lat = float(latitude) if latitude else None
    lng = float(longitude) if longitude else None

    total = sum(item.total_cost for item in cart_items)
    amount_paise = int(total * 100)

    buy_now_pid = request.POST.get('buy_now', '').strip()
    if buy_now_pid:
        buy_now_items = cart_items.filter(product_id=buy_now_pid)
        cod_available = all(item.product.cash_on_delivery for item in buy_now_items) if buy_now_items.exists() else False
    else:
        cod_available = all(item.product.cash_on_delivery for item in cart_items)

    if method == 'COD' and not cod_available:
        return JsonResponse({'error': 'Cash on Delivery is not available for this product.'}, status=400)

    order = Order.objects.create(
        user=request.user,
        total_amount=total,
        address=full_address,
        pincode=pincode,
        latitude=lat,
        longitude=lng,
        phone=phone,
        status='Pending',
        payment_status='Pending'
    )

    save_address_from_post(request)

    notify_order_placed(request.user, order)

    # ── Cash on Delivery ── (order is placed immediately)
    if method == 'COD':
        create_order_items_from_cart(order, request.user)
        Payment.objects.create(
            user=request.user,
            order=order,
            amount=total,
            payment_gateway='COD',
            status='PENDING',
            gateway_response={'method': 'COD'},
        )
        generate_invoice_for_order(order)
        return JsonResponse({
            'status': 'success',
            'mode': 'cod',
            'db_order_id': order.id,
        })

    # ── Test/demo fallback: no keys loaded → simulated Razorpay checkout ──
    # (Order/Payment already created above. Lets the full flow run end-to-end
    # even when RAZORPAY_KEY_ID / SECRET are missing at runtime.)
    if not is_razorpay_configured():
        mock_order_id = 'mock_' + str(order.id)
        Payment.objects.create(
            user=request.user,
            order=order,
            amount=total,
            payment_gateway='RAZORPAY',
            razorpay_order_id=mock_order_id,
            status='PENDING',
            gateway_response={'method': method, 'mock': True},
        )
        return JsonResponse({
            'status': 'success',
            'mode': 'online',
            'mock': True,
            'razorpay_order_id': mock_order_id,
            'amount': amount_paise,
            'currency': 'INR',
            'prefilled_method': method,
            'db_order_id': order.id,
        })

    client = get_razorpay_client()
    try:
        rzp_order = client.order.create({
            'amount': amount_paise,
            'currency': 'INR',
            'payment_capture': '1',
            'notes': {'method': method},
        })
    except Exception as e:
        logger.error(f"Razorpay order creation failed: {e}")
        order.status = 'Cancelled'
        order.payment_status = 'FAILED'
        order.save()
        return JsonResponse({'error': 'Payment gateway error. Please try again.'}, status=500)

    order.razorpay_order_id = rzp_order['id']
    order.save()

    payment = Payment.objects.create(
        user=request.user,
        order=order,
        amount=total,
        payment_gateway='RAZORPAY',
        razorpay_order_id=rzp_order['id'],
        status='PENDING',
        gateway_response={'method': method},
    )

    return JsonResponse({
        'status': 'success',
        'mode': 'online',
        'razorpay_enabled': True,
        'razorpay_key_id': settings.RAZORPAY_KEY_ID,
        'razorpay_order_id': rzp_order['id'],
        'amount': amount_paise,
        'currency': 'INR',
        'prefilled_method': method,
        'db_order_id': order.id,
        'db_payment_id': payment.id,
    })


# ── Step 2: Verify Payment (AJAX) ──
def verify_payment(request):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Login required'}, status=401)
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request'}, status=400)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    razorpay_order_id = data.get('razorpay_order_id')
    razorpay_pay_id = data.get('razorpay_payment_id')
    razorpay_signature = data.get('razorpay_signature')

    if not all([razorpay_order_id, razorpay_pay_id, razorpay_signature]):
        return JsonResponse({'error': 'Missing payment details'}, status=400)

    # Mock/test orders are auto-verified and marked paid
    if razorpay_order_id.startswith('mock_'):
        try:
            payment = Payment.objects.get(razorpay_order_id=razorpay_order_id, user=request.user)
        except Payment.DoesNotExist:
            return JsonResponse({'error': 'Payment not found'}, status=404)
        payment.status = 'SUCCESS'
        payment.razorpay_pay_id = razorpay_pay_id
        payment.razorpay_signature = razorpay_signature
        payment.save()
        order = payment.order
        if order:
            create_order_items_from_cart(order, request.user)
            order.payment_status = 'Paid'
            order.status = 'Processing'
            order.razorpay_pay_id = razorpay_pay_id
            order.razorpay_signature = razorpay_signature
            order.save()
            notify_payment_success(order.user, order)
            notify_order_confirmed(order.user, order)
            generate_invoice_for_order(order)
            return JsonResponse({'status': 'success', 'order_id': order.id})
        return JsonResponse({'status': 'success', 'order_id': None})

    payment = get_object_or_404(Payment, razorpay_order_id=razorpay_order_id, user=request.user)

    if payment.is_success:
        return JsonResponse({'status': 'success', 'order_id': payment.order.id})

    client = get_razorpay_client()
    params_dict = {
        'razorpay_order_id': razorpay_order_id,
        'razorpay_payment_id': razorpay_pay_id,
        'razorpay_signature': razorpay_signature,
    }

    try:
        client.utility.verify_payment_signature(params_dict)
    except razorpay.errors.SignatureVerificationError:
        payment.status = 'FAILED'
        payment.gateway_response = params_dict
        payment.save()
        if payment.order:
            payment.order.payment_status = 'FAILED'
            payment.order.save()
            notify_payment_failed(payment.order.user, payment.order)
        return JsonResponse({'error': 'Payment verification failed'}, status=400)

    payment.razorpay_pay_id = razorpay_pay_id
    payment.razorpay_signature = razorpay_signature
    payment.status = 'SUCCESS'
    payment.gateway_response = {'verification': 'passed'}
    payment.save()

    order = payment.order
    if order and order.payment_status != 'Paid':
        create_order_items_from_cart(order, request.user)
        order.payment_status = 'Paid'
        order.razorpay_pay_id = razorpay_pay_id
        order.razorpay_signature = razorpay_signature
        order.status = 'Processing'
        order.save()
        notify_payment_success(order.user, order)
        notify_order_confirmed(order.user, order)
        generate_invoice_for_order(order)

    return JsonResponse({'status': 'success', 'order_id': order.id if order else None})


# ── Step 3: Payment Status Pages ──

def payment_success(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)
    return render(request, 'shop/payment_success.html', {'order': order})


def payment_failed(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)
    if order.payment_status != 'Paid':
        order.payment_status = 'FAILED'
        order.status = 'Cancelled'
        order.save()
        notify_payment_failed(order.user, order)
        notify_order_cancelled(order.user, order)
    return render(request, 'shop/payment_failed.html', {'order': order})


def payment_cancelled(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)
    if order.payment_status != 'Paid':
        order.payment_status = 'CANCELLED'
        order.status = 'Cancelled'
        order.save()
        notify_payment_failed(order.user, order)
        notify_order_cancelled(order.user, order)
    return render(request, 'shop/payment_cancelled.html', {'order': order})


# ═══════════════════════════════════════════
# ── Notifications ──
# ═══════════════════════════════════════════

def _user_notifications(user):
    return Notification.objects.filter(user=user)


def notifications_data(request):
    """Return the notification panel HTML + unread count for the bell."""
    if not request.user.is_authenticated:
        return JsonResponse({'unread_count': 0, 'html': ''}, status=401)
    notifications = _user_notifications(request.user)[:50]
    unread_count = _user_notifications(request.user).filter(is_read=False).count()
    html = render_to_string(
        'shop/inc/notification_panel.html',
        {'notifications': notifications},
        request=request,
    )
    return JsonResponse({'unread_count': unread_count, 'html': html})


def notification_mark_read(request, nid):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Login required'}, status=401)
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request'}, status=400)
    _user_notifications(request.user).filter(id=nid).update(is_read=True)
    unread_count = _user_notifications(request.user).filter(is_read=False).count()
    return JsonResponse({'status': 'success', 'unread_count': unread_count})


def notification_mark_all_read(request):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Login required'}, status=401)
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request'}, status=400)
    _user_notifications(request.user).filter(is_read=False).update(is_read=True)
    return JsonResponse({'status': 'success', 'unread_count': 0})


def notification_delete(request, nid):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Login required'}, status=401)
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request'}, status=400)
    _user_notifications(request.user).filter(id=nid).delete()
    unread_count = _user_notifications(request.user).filter(is_read=False).count()
    return JsonResponse({'status': 'success', 'unread_count': unread_count})


def notification_delete_all(request):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Login required'}, status=401)
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request'}, status=400)
    _user_notifications(request.user).delete()
    return JsonResponse({'status': 'success', 'unread_count': 0})


@staff_member_required(login_url='/login')
def admin_send_announcement(request):
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        message = request.POST.get('message', '').strip()
        if not title:
            messages.error(request, "Announcement title is required.")
            return redirect('admin_send_announcement')
        users = User.objects.filter(is_active=True)
        created = notify_many(users, 'announcement', title[:255], message, link='/')
        messages.success(request, f"Announcement sent to {created} users.")
        return redirect('admin_send_announcement')
    return render(request, 'shop/admin/announcement_form.html')


# ── Step 4: Webhook (CSRF exempt) ──

@csrf_exempt
def payment_webhook(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid method'}, status=405)

    webhook_signature = request.headers.get('X-Razorpay-Signature', '')
    webhook_secret = settings.RAZORPAY_WEBHOOK_SECRET

    try:
        client = razorpay.Client(auth=('', ''))
        client.utility.verify_webhook_signature(
            request.body,
            webhook_signature,
            webhook_secret
        )
    except razorpay.errors.SignatureVerificationError:
        logger.warning("Webhook signature verification failed")
        return JsonResponse({'error': 'Invalid signature'}, status=400)

    try:
        event = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    event_type = event.get('event', '')
    payload = event.get('payload', {})
    rzp_order_id = payload.get('order', {}).get('id', '')
    rzp_pay_id = payload.get('payment', {}).get('id', '')

    if not rzp_order_id:
        return JsonResponse({'error': 'Missing order ID'}, status=400)

    try:
        payment = Payment.objects.get(razorpay_order_id=rzp_order_id)
    except Payment.DoesNotExist:
        logger.warning(f"Webhook: Payment not found for order {rzp_order_id}")
        return JsonResponse({'error': 'Payment not found'}, status=404)

    # Prevent duplicate processing
    if payment.is_success and event_type in ('payment.captured', 'order.paid'):
        return JsonResponse({'status': 'already_processed'})

    if event_type in ('payment.captured', 'order.paid'):
        payment.status = 'SUCCESS'
        payment.razorpay_pay_id = rzp_pay_id or payment.razorpay_pay_id
        payment.gateway_response = event
        payment.save()

        order = payment.order
        if order and order.payment_status != 'Paid':
            create_order_items_from_cart(order, order.user)
            order.payment_status = 'Paid'
            order.razorpay_pay_id = rzp_pay_id or order.razorpay_pay_id
            order.status = 'Processing'
            order.save()
            notify_payment_success(order.user, order)
            notify_order_confirmed(order.user, order)
            generate_invoice_for_order(order)

    elif event_type == 'payment.failed':
        payment.status = 'FAILED'
        payment.gateway_response = event
        payment.save()
        if payment.order:
            payment.order.payment_status = 'FAILED'
            payment.order.save()
            notify_payment_failed(payment.order.user, payment.order)

    return JsonResponse({'status': 'ok'})


# ── My Orders ──
def my_orders(request):
    if not request.user.is_authenticated:
        return redirect("/login")
    orders = Order.objects.filter(user=request.user).order_by('-created_at')
    order_item_ids = set()
    for o in orders:
        order_item_ids.update(o.items.values_list('id', flat=True))
    rated_item_ids = set(
        ProductRating.objects.filter(user=request.user, order_item_id__in=order_item_ids)
        .values_list('order_item_id', flat=True)
    )
    now = timezone.now()
    cutoff = now - timedelta(days=7)
    rating_open_item_ids = set()
    for o in orders.filter(status='Delivered'):
        delivered_at = o.delivered_at or o.updated_at
        if delivered_at and delivered_at >= cutoff:
            for oi_id in o.items.values_list('id', flat=True):
                if oi_id not in rated_item_ids:
                    rating_open_item_ids.add(oi_id)
    return render(request, 'shop/my_orders.html', {
        'orders': orders,
        'rated_item_ids': rated_item_ids,
        'rating_open_item_ids': rating_open_item_ids,
    })


# ── Invoice PDF ──
def order_invoice_pdf(request, oid):
    """Download the PDF invoice for an order owned by the user.

    Works for both Razorpay and Cash on Delivery orders at any active
    stage (Pending / Processing / Shipped / Delivered). The PDF is
    generated dynamically from the Invoice snapshot on each request —
    no static file is stored. Cancelled orders do not get an invoice.
    """
    if not request.user.is_authenticated:
        return redirect('/login')

    order = get_object_or_404(Order, id=oid, user=request.user)
    if order.status == 'Cancelled':
        raise Http404("Invoice is not available for a cancelled order.")

    invoice = getattr(order, 'invoice', None)
    if invoice is None:
        invoice = generate_invoice_for_order(order)
        if invoice is None:
            raise Http404("Invoice could not be generated.")

    from shop.invoicing import render_invoice_pdf

    payload = render_invoice_pdf(invoice)
    filename = f"invoice_{invoice.invoice_number}.pdf"
    response = HttpResponse(payload, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response['Cache-Control'] = 'no-store'
    return response


# ── Product Rating (after delivery) ──
def submit_rating(request):
    if not request.user.is_authenticated:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'error': 'Login required'}, status=401)
        return redirect('/login')

    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request'}, status=400)

    try:
        value = int(request.POST.get('rating'))
    except (TypeError, ValueError):
        return JsonResponse({'error': 'Please select a star rating.'}, status=400)
    if value < 1 or value > 5:
        return JsonResponse({'error': 'Rating must be between 1 and 5 stars.'}, status=400)

    order_item_id = request.POST.get('order_item_id')
    if not order_item_id:
        return JsonResponse({'error': 'Missing order item.'}, status=400)

    try:
        order_item = OrderItem.objects.select_related('order', 'product').get(id=order_item_id)
    except (OrderItem.DoesNotExist, ValueError, TypeError):
        return JsonResponse({'error': 'Invalid order item.'}, status=400)

    if order_item.order.user != request.user:
        return JsonResponse({'error': 'This order does not belong to you.'}, status=403)

    if order_item.order.status != 'Delivered':
        return JsonResponse({'error': 'You can rate a product only after your order is delivered.'}, status=403)

    delivered_at = order_item.order.delivered_at or order_item.order.updated_at
    if delivered_at and timezone.now() > delivered_at + timedelta(days=7):
        return JsonResponse({'error': 'The 7-day review window for this order has ended. Rating is no longer available.'}, status=403)

    if ProductRating.objects.filter(order_item=order_item).exists():
        return JsonResponse({'error': 'You have already reviewed this purchase.'}, status=400)

    comment = (request.POST.get('comment') or '').strip()[:500]

    media_files = request.FILES.getlist('media')
    if not media_files:
        single = request.FILES.get('image')
        if single:
            media_files = [single]

    if len(media_files) > 6:
        return JsonResponse({'error': 'You can upload up to 6 photos or videos.'}, status=400)

    allowed_image_ext = ('jpg', 'jpeg', 'png', 'webp')
    allowed_video_ext = ('mp4', 'webm', 'mov')
    normalized = []
    for f in media_files:
        ext = (f.name.rsplit('.', 1)[-1] if '.' in f.name else '').lower()
        ctype = (f.content_type or '').lower()
        if ext in allowed_image_ext and ctype.startswith('image/'):
            normalized.append((f, 'image'))
        elif ext in allowed_video_ext and ctype.startswith('video/'):
            normalized.append((f, 'video'))
        else:
            return JsonResponse({'error': 'Only JPG, JPEG, PNG, WEBP images and MP4, WEBM, MOV videos are allowed.'}, status=400)

    rating = ProductRating.objects.create(
        product=order_item.product,
        user=request.user,
        order_item=order_item,
        rating=value,
        comment=comment,
    )
    for f, mtype in normalized:
        ProductRatingMedia.objects.create(
            rating=rating,
            file=f,
            media_type=mtype,
        )
    return JsonResponse({'ok': True, 'created': True, 'rating': value})


# ── Profile / Account Details ──
def profile_page(request):
    if not request.user.is_authenticated:
        return redirect("/login")
    profile = UserProfile.objects.filter(user=request.user).first()
    return render(request, 'shop/profile.html', {
        'profile': profile,
        'orders_count': Order.objects.filter(user=request.user).count(),
        'saved_addresses': SavedAddress.objects.filter(user=request.user),
    })


def edit_profile(request):
    if not request.user.is_authenticated:
        return redirect("/login")

    profile = UserProfile.objects.filter(user=request.user).first()
    if not profile:
        profile = UserProfile.objects.create(user=request.user)

    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        phone = request.POST.get('phone', '').strip()

        if not first_name or not last_name:
            messages.error(request, "Please enter your first and last name.")
            return redirect('edit_profile')

        normalized = _normalize_mobile(phone)
        if not _is_valid_mobile(normalized):
            messages.error(request, "Please enter a valid 10-digit mobile number starting with 6-9.")
            return redirect('edit_profile')

        if UserProfile.objects.filter(mobile_number=normalized).exclude(user=request.user).exists():
            messages.error(request, "This mobile number is already linked to another account.")
            return redirect('edit_profile')

        user = request.user
        user.first_name = first_name[:30]
        user.last_name = last_name[:150]
        user.save()
        profile.mobile_number = normalized
        profile.save()
        messages.success(request, "Profile updated successfully.")
        return redirect('profile')

    return render(request, 'shop/edit_profile.html', {
        'profile': profile,
    })


def change_profile_picture(request):
    if not request.user.is_authenticated:
        return redirect("/login")

    profile = UserProfile.objects.filter(user=request.user).first()
    if not profile:
        profile = UserProfile.objects.create(user=request.user)

    if request.method == 'POST' and request.FILES.get('profile_picture'):
        pic = request.FILES['profile_picture']
        if not pic.content_type.startswith('image/'):
            messages.error(request, "Please choose an image file.")
            return redirect('profile')
        profile.profile_picture = optimize_image(pic)
        profile.save()
        messages.success(request, "Profile picture updated.")
    else:
        messages.error(request, "No image selected.")
    return redirect('profile')


def delete_profile_picture(request):
    if not request.user.is_authenticated:
        return redirect("/login")

    profile = UserProfile.objects.filter(user=request.user).first()
    if profile and profile.profile_picture:
        old_name = profile.profile_picture.name
        profile.profile_picture = None
        profile.save()
        delete_image_file(old_name)
        messages.success(request, "Profile picture removed.")
    else:
        messages.error(request, "No profile picture to remove.")
    return redirect('profile')


# ── Cancel Order ──
def cancel_order(request, oid):
    if not request.user.is_authenticated:
        return redirect("/login")
    try:
        order = Order.objects.get(id=oid, user=request.user)
        if order.status in ['Pending', 'Processing']:
            reason = request.POST.get('reason', '').strip()
            order.status = 'Cancelled'
            order.cancel_reason = reason or None
            order.cancelled_at = timezone.now()
            order.save()
            notify_order_cancelled(order.user, order, reason)
            messages.success(request, "Your order has been cancelled.")
        else:
            messages.error(request, f"Your order cannot be cancelled as it is already {order.status}.")
    except Order.DoesNotExist:
        messages.error(request, "Order not found.")
    return redirect("/my_orders")


# ── Update Alternate Phone (AJAX) ──
def update_alternate_phone(request, oid):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Login required'}, status=401)
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request'}, status=400)
    if request.user.is_staff or request.user.is_superuser:
        order = get_object_or_404(Order, id=oid)
    else:
        order = get_object_or_404(Order, id=oid, user=request.user)
    phone = request.POST.get('phone', '').strip()
    digits = ''.join(ch for ch in phone if ch.isdigit())
    if not digits:
        order.alternate_phone = ''
        order.save()
        return JsonResponse({'status': 'success', 'alternate_phone': ''})
    if len(digits) != 10:
        return JsonResponse({'error': 'Enter a valid 10-digit phone number.'}, status=400)
    order.alternate_phone = digits
    order.save()
    return JsonResponse({'status': 'success', 'alternate_phone': order.alternate_phone})


def delete_address(request):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Login required'}, status=401)
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request'}, status=400)
    address_id = request.POST.get('address_id', '').strip()
    if not address_id:
        return JsonResponse({'error': 'Missing address id'}, status=400)
    deleted = SavedAddress.objects.filter(id=address_id, user=request.user).delete()[0]
    if not deleted:
        return JsonResponse({'error': 'Address not found'}, status=404)
    return JsonResponse({'status': 'success'})


def add_address(request):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Login required'}, status=401)
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request'}, status=400)
    address = request.POST.get('address', '').strip()
    pincode = request.POST.get('pincode', '').strip()
    locality = request.POST.get('locality', '').strip()
    phone = request.POST.get('phone', '').strip()
    if not address or not pincode or not locality:
        return JsonResponse({'error': 'Address, pincode and locality are required'}, status=400)
    phone_digits = ''.join(ch for ch in phone if ch.isdigit())
    if len(phone_digits) != 10:
        return JsonResponse({'error': 'Enter a valid 10-digit phone number.'}, status=400)
    label = request.POST.get('label', '').strip()
    if not label:
        label = f"Address {request.user.saved_addresses.count() + 1}"
    lat_str = request.POST.get('latitude', '').strip()
    lng_str = request.POST.get('longitude', '').strip()
    sa = SavedAddress.objects.create(
        user=request.user,
        label=label,
        address=address,
        locality=request.POST.get('locality', '').strip(),
        landmark=request.POST.get('landmark', '').strip(),
        pincode=pincode,
        phone=request.POST.get('phone', '').strip(),
        latitude=float(lat_str) if lat_str else None,
        longitude=float(lng_str) if lng_str else None,
    )
    return JsonResponse({'status': 'success', 'id': sa.id, 'label': sa.label})


def logout_page(request):
    if request.user.is_authenticated:
        logout(request)
        messages.success(request, "Logged out Successfully")
    return redirect("/")


# ═══════════════════════════════════════════
# ── Passwordless OTP Login / Account Creation ──
# ═══════════════════════════════════════════

LOGIN_OTP_VALID_MINUTES = 5
LOGIN_OTP_COOLDOWN_SECONDS = 60
LOGIN_OTP_MAX_ATTEMPTS = 5
LOGIN_OTP_PER_WINDOW = 5
LOGIN_OTP_WINDOW_MINUTES = 10


def _mask_email(email):
    local, _, domain = email.partition('@')
    if len(local) <= 2:
        masked = local[0] + '***'
    else:
        masked = local[:2] + '*' * (len(local) - 2)
    return f"{masked}@{domain}"


def _issue_login_otp(email, is_new):
    """Rate-limited OTP issuance. Returns (ok, error_message)."""
    recent = LoginOTP.objects.filter(
        identifier=email,
        is_used=False,
        created_at__gte=timezone.now() - timedelta(seconds=LOGIN_OTP_COOLDOWN_SECONDS),
    ).exists()
    if recent:
        return False, "Please wait 60 seconds before requesting another OTP."

    window_start = timezone.now() - timedelta(minutes=LOGIN_OTP_WINDOW_MINUTES)
    count = LoginOTP.objects.filter(identifier=email, created_at__gte=window_start).count()
    if count >= LOGIN_OTP_PER_WINDOW:
        return False, "Too many OTP requests. Please try again after a few minutes."

    # Invalidate any previous active OTPs (prevent reuse).
    LoginOTP.objects.filter(identifier=email, is_used=False).update(is_used=True)

    otp = _generate_otp()
    LoginOTP.objects.create(
        identifier=email,
        otp_hash=make_password(otp),
        expires_at=timezone.now() + timedelta(minutes=LOGIN_OTP_VALID_MINUTES),
    )

    user = User.objects.filter(email__iexact=email).first()
    to_email = user.email if user else email
    sent = send_otp_email(to_email, otp, purpose="login")

    if not sent:
        return False, "Could not send the OTP right now. Please try again later."
    return True, None


def _normalize_mobile(value):
    digits = ''.join(ch for ch in str(value) if ch.isdigit())
    return digits[-10:] if len(digits) >= 10 else digits


def _is_valid_mobile(value):
    return re.fullmatch(r'[6-9]\d{9}', value) is not None


ADMIN_EMAIL = 'kaviyarasank317@gmail.com'


def _resolve_or_create_user(email, first_name='', last_name='', phone=''):
    user = User.objects.filter(email__iexact=email).first()
    if not user:
        user = User.objects.create_user(
            username=email,
            email=email,
            first_name=first_name[:30],
            last_name=last_name[:150],
        )
        if phone:
            phone_taken = UserProfile.objects.filter(mobile_number=phone).exclude(user=user).exists()
            UserProfile.objects.create(
                user=user,
                mobile_number=None if phone_taken else phone,
            )
    if user.email and user.email.lower() == ADMIN_EMAIL and not user.is_staff:
        user.is_staff = True
        user.is_superuser = True
        user.save()
    return user


# ═══════════════════════════════════════════
# ── Google Sign-In (OAuth 2.0) ──
# ═══════════════════════════════════════════

GOOGLE_NONCE_SESSION_KEY = 'google_auth_nonce'


def _google_nonce(request):
    """Return the per-session nonce used to bind the Google ID token to this browser."""
    nonce = request.session.get(GOOGLE_NONCE_SESSION_KEY)
    if not nonce:
        nonce = secrets.token_urlsafe(32)
        request.session[GOOGLE_NONCE_SESSION_KEY] = nonce
    return nonce


def _google_auth_context(request):
    return {
        'google_client_id': settings.GOOGLE_CLIENT_ID,
        'google_nonce': _google_nonce(request),
        'google_signin_debug': settings.DEBUG,
        'google_signin_enabled': bool(settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET),
        'google_redirect_uri': request.build_absolute_uri(reverse('google_callback')),
    }


def google_auth(request):
    """Validate the Google ID token posted by the Sign-In button and log the user in.

    The token is verified on the server with the official google-auth library
    (signature, issuer, audience and expiry). Only a verified Google email is
    trusted; it is matched case-insensitively to an existing account or used to
    create a new one, so no duplicate accounts can appear.
    """
    if request.user.is_authenticated:
        return JsonResponse({'ok': True})

    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'Invalid request.'})

    credential = request.POST.get('credential', '').strip()
    if not credential:
        return JsonResponse({'ok': False, 'error': 'Google Sign-In was cancelled. Please try again or use email + OTP.'})

    client_id = settings.GOOGLE_CLIENT_ID
    if not client_id:
        logger.warning("Google Sign-In attempted but GOOGLE_CLIENT_ID is not configured.")
        return JsonResponse({'ok': False, 'error': 'Google Sign-In is not configured yet. Please use email + OTP to log in.'})

    try:
        import google.auth.transport.requests
        import google.oauth2.id_token

        idinfo = google.oauth2.id_token.verify_oauth2_token(
            credential,
            google.auth.transport.requests.Request(),
            client_id,
        )
    except ValueError as exc:
        logger.warning("Google token verification rejected: %s", exc)
        return JsonResponse({'ok': False, 'error': 'Could not verify your Google account. Please try again.'})
    except ImportError:
        logger.error("google-auth is not installed; add 'google-auth' to requirements.txt.")
        return JsonResponse({'ok': False, 'error': 'Google Sign-In is not available right now. Please use email + OTP.'})
    except Exception as exc:
        logger.exception("Google token verification failed: %s", exc)
        return JsonResponse({'ok': False, 'error': 'Could not verify your Google account. Please try again later.'})

    expected_nonce = request.session.get(GOOGLE_NONCE_SESSION_KEY)
    if not expected_nonce or idinfo.get('nonce') != expected_nonce:
        logger.warning("Google nonce mismatch (possible replay/CSRF attempt).")
        return JsonResponse({'ok': False, 'error': 'Security check failed. Please refresh the page and try again.'})

    if idinfo.get('iss') not in ('accounts.google.com', 'https://accounts.google.com'):
        return JsonResponse({'ok': False, 'error': 'Could not verify your Google account. Please try again.'})

    if idinfo.get('aud') != client_id:
        logger.warning("Google token audience mismatch (expected %s).", client_id)
        return JsonResponse({'ok': False, 'error': 'Could not verify your Google account. Please try again.'})

    if not idinfo.get('email_verified'):
        return JsonResponse({'ok': False, 'error': 'Please verify your email address with Google, then sign in again.'})

    email = (idinfo.get('email') or '').strip().lower()
    if not email:
        return JsonResponse({'ok': False, 'error': 'Google did not provide an email address for your account.'})

    full_name = (idinfo.get('name') or '').strip()
    name_parts = full_name.split()
    first_name = name_parts[0] if name_parts else ''
    last_name = ' '.join(name_parts[1:]) if len(name_parts) > 1 else ''
    if not first_name:
        first_name = email.split('@')[0]

    user = _resolve_or_create_user(email, first_name=first_name, last_name=last_name)

    user.backend = 'django.contrib.auth.backends.ModelBackend'
    login(request, user)

    profile, _ = UserProfile.objects.get_or_create(user=user)
    if not profile.profile_picture:
        google_pic = fetch_google_picture(idinfo.get('picture'))
        if google_pic:
            try:
                profile.profile_picture = optimize_image(google_pic, max_size=300)
                profile.save()
            except Exception:
                pass
        if not profile.profile_picture:
            gravatar = fetch_gravatar(user.email)
            if gravatar:
                try:
                    profile.profile_picture = optimize_image(gravatar, max_size=300)
                    profile.save()
                except Exception:
                    pass

    request.session.pop(GOOGLE_NONCE_SESSION_KEY, None)
    notify_login_new_device(user)
    messages.success(request, "Logged in successfully with Google!")
    return JsonResponse({'ok': True})


GOOGLE_OAUTH_STATE_SESSION_KEY = 'google_oauth_state'
GOOGLE_OAUTH_NEXT_SESSION_KEY = 'google_oauth_next'


def _google_safe_next(request):
    """Return a safe internal redirect target for after Google login."""
    next_url = request.GET.get('next') or '/'
    if not next_url.startswith('/') or next_url.startswith('//'):
        next_url = '/'
    return next_url


def google_login(request):
    """Start the Google OAuth 2.0 authorization-code flow (full-page redirect)."""
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        messages.error(request, "Google Sign-In is not configured. Please use email + OTP.")
        return redirect('login')

    if request.user.is_authenticated:
        return redirect(_google_safe_next(request))

    state = secrets.token_urlsafe(32)
    request.session[GOOGLE_OAUTH_STATE_SESSION_KEY] = state
    request.session[GOOGLE_OAUTH_NEXT_SESSION_KEY] = _google_safe_next(request)

    redirect_uri = request.build_absolute_uri(reverse('google_callback'))
    logger.info(
        "Google OAuth login started. redirect_uri=%s - this exact URI (no trailing slash) "
        "must be listed under Authorized redirect URIs in Google Cloud Console.", redirect_uri
    )

    params = {
        'client_id': settings.GOOGLE_CLIENT_ID,
        'redirect_uri': redirect_uri,
        'response_type': 'code',
        'scope': 'openid email profile',
        'access_type': 'online',
        'prompt': 'select_account',
        'state': state,
        'include_granted_scopes': 'true',
    }
    auth_url = 'https://accounts.google.com/o/oauth2/v2/auth?' + urllib.parse.urlencode(params)
    return redirect(auth_url)


def _google_exchange_code(code, redirect_uri):
    """Exchange the authorization code for tokens at Google's token endpoint."""
    body = urllib.parse.urlencode({
        'code': code,
        'client_id': settings.GOOGLE_CLIENT_ID,
        'client_secret': settings.GOOGLE_CLIENT_SECRET,
        'redirect_uri': redirect_uri,
        'grant_type': 'authorization_code',
    }).encode('utf-8')
    req = urllib.request.Request(
        'https://oauth2.googleapis.com/token',
        data=body,
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode('utf-8'))


def google_callback(request):
    """Handle Google's redirect back after the user signs in, then log them in."""
    if request.GET.get('error'):
        messages.error(request, "Google Sign-In was cancelled.")
        return redirect('login')

    expected_state = request.session.pop(GOOGLE_OAUTH_STATE_SESSION_KEY, None)
    next_url = request.session.pop(GOOGLE_OAUTH_NEXT_SESSION_KEY, '/')
    if not next_url.startswith('/') or next_url.startswith('//'):
        next_url = '/'

    state = request.GET.get('state', '')
    if not expected_state or not secrets.compare_digest(state, expected_state):
        messages.error(request, "Security check failed. Please try signing in with Google again.")
        return redirect('login')

    code = request.GET.get('code', '')
    if not code:
        messages.error(request, "Google Sign-In did not return a code. Please try again.")
        return redirect('login')

    redirect_uri = request.build_absolute_uri(reverse('google_callback'))
    try:
        token_data = _google_exchange_code(code, redirect_uri)
    except Exception as exc:
        logger.exception("Google token exchange failed: %s", exc)
        messages.error(request, "Could not sign in with Google. Please try again.")
        return redirect('login')

    id_token = (token_data or {}).get('id_token')
    if not id_token:
        messages.error(request, "Google Sign-In did not return an identity token. Please try again.")
        return redirect('login')

    try:
        import google.auth.transport.requests
        import google.oauth2.id_token
        idinfo = google.oauth2.id_token.verify_oauth2_token(
            id_token,
            google.auth.transport.requests.Request(),
            settings.GOOGLE_CLIENT_ID,
        )
    except Exception as exc:
        logger.exception("Google token verification failed: %s", exc)
        messages.error(request, "Could not verify your Google account. Please try again.")
        return redirect('login')

    if idinfo.get('iss') not in ('accounts.google.com', 'https://accounts.google.com'):
        messages.error(request, "Could not verify your Google account. Please try again.")
        return redirect('login')
    if idinfo.get('aud') != settings.GOOGLE_CLIENT_ID:
        messages.error(request, "Could not verify your Google account. Please try again.")
        return redirect('login')
    if not idinfo.get('email_verified'):
        messages.error(request, "Please verify your email address with Google, then sign in again.")
        return redirect('login')

    email = (idinfo.get('email') or '').strip().lower()
    if not email:
        messages.error(request, "Google did not provide an email address for your account.")
        return redirect('login')

    full_name = (idinfo.get('name') or '').strip()
    name_parts = full_name.split()
    first_name = name_parts[0] if name_parts else ''
    last_name = ' '.join(name_parts[1:]) if len(name_parts) > 1 else ''
    if not first_name:
        first_name = email.split('@')[0]

    user = _resolve_or_create_user(email, first_name=first_name, last_name=last_name)
    user.backend = 'django.contrib.auth.backends.ModelBackend'
    login(request, user)

    profile, _ = UserProfile.objects.get_or_create(user=user)
    if not profile.profile_picture:
        google_pic = fetch_google_picture(idinfo.get('picture'))
        if google_pic:
            try:
                profile.profile_picture = optimize_image(google_pic, max_size=300)
                profile.save()
            except Exception:
                pass
        if not profile.profile_picture:
            gravatar = fetch_gravatar(user.email)
            if gravatar:
                try:
                    profile.profile_picture = optimize_image(gravatar, max_size=300)
                    profile.save()
                except Exception:
                    pass

    notify_login_new_device(user)
    messages.success(request, "Logged in successfully with Google!")
    return redirect(next_url)


def login_page(request):
    if request.user.is_authenticated:
        return redirect("/")

    mode = 'new' if request.GET.get('mode') == 'new' else 'login'

    form_data = {
        'first_name': request.POST.get('first_name', ''),
        'last_name': request.POST.get('last_name', ''),
        'phone': request.POST.get('phone', ''),
        'identifier': request.POST.get('identifier', request.GET.get('identifier', '')),
    }
    field_errors = {}

    if request.method == 'POST':
        mode = 'new' if request.POST.get('mode') == 'new' else 'login'
        identifier = request.POST.get('identifier', '').strip().lower()
        form_data['identifier'] = identifier
        context = {
            'mode': mode,
            'form': form_data,
            'field_errors': field_errors,
            **_google_auth_context(request),
        }

        if not identifier:
            field_errors['identifier'] = "Please enter your email address."
            return render(request, "shop/login.html", context)

        if '@' not in identifier:
            field_errors['identifier'] = "Please enter your email address (e.g. name@example.com)."
            return render(request, "shop/login.html", context)

        exists = User.objects.filter(email__iexact=identifier).exists()
        if mode == 'new' and exists:
            field_errors['identifier'] = "An account with this email already exists. Please log in instead."
            return render(request, "shop/login.html", {
                'mode': 'login', 'form': form_data, 'field_errors': field_errors,
                **_google_auth_context(request),
            })
        elif mode == 'login' and not exists:
            field_errors['identifier'] = "No account found with this email. Please create an account."
            return render(request, "shop/login.html", {
                'mode': 'new', 'form': form_data, 'field_errors': field_errors,
                **_google_auth_context(request),
            })
        is_new = not exists

        first_name = last_name = phone = ''
        if mode == 'new' and is_new:
            first_name = request.POST.get('first_name', '').strip()
            last_name = request.POST.get('last_name', '').strip()
            phone = _normalize_mobile(request.POST.get('phone', ''))
            form_data['first_name'] = first_name
            form_data['last_name'] = last_name
            form_data['phone'] = phone
            if not first_name:
                field_errors['first_name'] = "Please enter your first name."
                return render(request, "shop/login.html", context)
            if not last_name:
                field_errors['last_name'] = "Please enter your last name."
                return render(request, "shop/login.html", context)
            if not _is_valid_mobile(phone):
                field_errors['phone'] = "Enter a valid 10-digit mobile number."
                return render(request, "shop/login.html", context)

        ok, err = _issue_login_otp(identifier, is_new)
        if not ok:
            messages.error(request, err)
            return render(request, "shop/login.html", context)

        request.session['login_identifier'] = identifier
        request.session['login_is_new'] = is_new
        if mode == 'new' and is_new:
            request.session['login_first_name'] = first_name
            request.session['login_last_name'] = last_name
            request.session['login_phone'] = phone
        else:
            request.session.pop('login_first_name', None)
            request.session.pop('login_last_name', None)
            request.session.pop('login_phone', None)
        if is_new:
            messages.info(request, "No account found — entering the OTP will create a new account for you.")
        else:
            messages.success(request, "OTP sent to your email address.")
        return redirect('verify_login_otp')

    return render(request, "shop/login.html", {
        'mode': mode,
        'form': form_data,
        'field_errors': field_errors,
        **_google_auth_context(request),
    })


def verify_login_otp(request):
    if request.user.is_authenticated:
        return redirect("/")

    identifier = request.session.get('login_identifier')
    if not identifier:
        messages.error(request, "Session expired. Please request a new OTP.")
        return redirect('login')

    if request.method == 'POST':
        otp = request.POST.get('otp', '').strip()
        if not otp.isdigit() or len(otp) != 6:
            messages.error(request, "Invalid OTP. Enter the 6-digit code.")
            return redirect('verify_login_otp')

        record = LoginOTP.objects.filter(
            identifier=identifier,
            is_used=False,
            expires_at__gt=timezone.now(),
        ).order_by('-created_at').first()

        if not record:
            messages.error(request, "Invalid or expired OTP. Please request a new one.")
            return redirect('login')

        if record.attempts >= LOGIN_OTP_MAX_ATTEMPTS:
            record.is_used = True
            record.save()
            messages.error(request, "Too many incorrect attempts. Please request a new OTP.")
            return redirect('login')

        record.attempts += 1
        record.save()

        if check_password(otp, record.otp_hash):
            record.is_used = True
            record.save()
            LoginOTP.objects.filter(identifier=identifier, is_used=False).update(is_used=True)

            user = _resolve_or_create_user(
                identifier,
                first_name=request.session.get('login_first_name', ''),
                last_name=request.session.get('login_last_name', ''),
                phone=request.session.get('login_phone', ''),
            )
            user.backend = 'django.contrib.auth.backends.ModelBackend'
            login(request, user)

            profile, _ = UserProfile.objects.get_or_create(user=user)
            if not profile.profile_picture:
                gravatar = fetch_gravatar(user.email)
                if gravatar:
                    profile.profile_picture = optimize_image(gravatar, max_size=300)
                    profile.save()

            request.session.pop('login_identifier', None)
            request.session.pop('login_is_new', None)
            request.session.pop('login_first_name', None)
            request.session.pop('login_last_name', None)
            request.session.pop('login_phone', None)
            notify_login_new_device(user)
            messages.success(request, "Logged in successfully!")
            return redirect("/")

        if record.attempts >= LOGIN_OTP_MAX_ATTEMPTS:
            record.is_used = True
            record.save()
            messages.error(request, "Too many incorrect attempts. Please request a new OTP.")
            return redirect('login')

        messages.error(request, "Incorrect OTP. Please try again.")
        return redirect('verify_login_otp')

    return render(request, "shop/verify_login_otp.html", {
        'identifier': _mask_email(identifier),
        'is_new': request.session.get('login_is_new', False),
    })


def resend_login_otp(request):
    if request.user.is_authenticated:
        return redirect("/")

    identifier = request.session.get('login_identifier')
    if not identifier:
        messages.error(request, "Session expired. Please start again.")
        return redirect('login')

    ok, err = _issue_login_otp(identifier, request.session.get('login_is_new', False))
    if not ok:
        messages.error(request, err)
    else:
        messages.success(request, "A new OTP has been sent.")
    return redirect('verify_login_otp')


def register(request):
    return redirect('/login?mode=new')


def _generate_otp():
    return f"{secrets.randbelow(1000000):06d}"




def collections(request):
    catagory = Catagory.objects.filter(status=0)
    return render(request, "shop/collections.html", {"catagory": catagory})


def collectionsview(request, name):
    if Catagory.objects.filter(name=name, status=0):
        products = Product.objects.filter(category__name=name).annotate(
            avg_rating=Avg('ratings__rating'),
            rating_count=Count('ratings'),
        )
        return render(request, "shop/products/index.html", {"products": products, "category_name": name})
    else:
        messages.warning(request, "No Such Catagory Found")
        return redirect('collections')


def product_details(request, cname, pname):
    if Catagory.objects.filter(name=cname, status=0):
        if Product.objects.filter(name=pname, status=0):
            products = Product.objects.filter(name=pname, status=0).first()
            # check if already in favourites
            is_fav = False
            if request.user.is_authenticated:
                is_fav = Favourite.objects.filter(user=request.user, product=products).exists()
            save_amount = products.original_price - products.selling_price
            related_products = list(
                Product.objects.filter(category=products.category, status=0)
                .annotate(
                    avg_rating=Avg('ratings__rating'),
                    rating_count=Count('ratings'),
                )
                .exclude(id=products.id)
                .order_by('-trending', '-created_at')[:12]
            )
            if len(related_products) < 6:
                exclude_ids = [p.id for p in related_products] + [products.id]
                related_products.extend(
                    Product.objects.filter(status=0)
                    .annotate(
                        avg_rating=Avg('ratings__rating'),
                        rating_count=Count('ratings'),
                    )
                    .exclude(id__in=exclude_ids)
                    .order_by('-trending', '-created_at')
                    [: (6 - len(related_products))]
                )
            my_rating = None
            rating_open = False
            eligible_order_item_id = None
            if request.user.is_authenticated:
                mr = ProductRating.objects.filter(product=products, user=request.user).order_by('-created_at').first()
                if mr:
                    my_rating = {'rating': mr.rating, 'comment': mr.comment}
                now = timezone.now()
                cutoff = now - timedelta(days=7)
                delivered_items = OrderItem.objects.filter(
                    product=products,
                    order__user=request.user,
                    order__status='Delivered',
                ).select_related('order')
                rated_oi_ids = set(
                    ProductRating.objects.filter(
                        product=products, user=request.user, order_item__isnull=False
                    ).values_list('order_item_id', flat=True)
                )
                for di in delivered_items:
                    delivered_at = di.order.delivered_at or di.order.updated_at
                    if delivered_at and delivered_at >= cutoff and di.id not in rated_oi_ids:
                        rating_open = True
                        eligible_order_item_id = di.id
                        break
            ratings_list = list(
                ProductRating.objects.filter(product=products).select_related('user').prefetch_related('media').order_by('-created_at')
            )
            rating_count = len(ratings_list)
            if rating_count:
                avg_rating = sum(r.rating for r in ratings_list) / rating_count
            else:
                avg_rating = 0
            rating_dist = []
            for star in range(5, 0, -1):
                star_count = sum(1 for r in ratings_list if r.rating == star)
                pct = round(star_count * 100 / rating_count) if rating_count else 0
                rating_dist.append({'star': star, 'count': star_count, 'pct': pct})
            verified_ids = set(
                OrderItem.objects.filter(product=products, order__status='Delivered')
                .values_list('order__user_id', flat=True)
            )
            review_media = []
            for r in ratings_list:
                items = []
                for m in r.media.all():
                    items.append({'url': m.file.url, 'type': m.media_type})
                if not items and r.image:
                    items.append({'url': r.image.url, 'type': 'image'})
                r.media_items = items
                r.first_media = items[0] if items else None
                for it in items:
                    review_media.append({
                        'url': it['url'],
                        'type': it['type'],
                        'user': r.user,
                        'rating': r.rating,
                        'verified': r.user.id in verified_ids,
                        'comment': r.comment or '',
                    })
            media_reviews = review_media
            return render(request, "shop/products/product_details.html", {
                "products": products,
                "is_fav": is_fav,
                "save_amount": save_amount,
                "related_products": related_products,
                "ratings": ratings_list,
                "rating_count": rating_count,
                "avg_rating": avg_rating,
                "rating_dist": rating_dist,
                "verified_ids": verified_ids,
                "media_reviews": media_reviews,
                "review_media": review_media,
                "my_rating": my_rating,
                "rating_open": rating_open,
                "eligible_order_item_id": eligible_order_item_id,
            })
        else:
            messages.error(request, "No Such Product Found")
            return redirect('collections')
    else:
        messages.error(request, "No Such Catagory Found")
        return redirect('collections')


# ═══════════════════════════════════════════
# ── Admin Dashboard ──
# ═══════════════════════════════════════════


@staff_member_required(login_url='/login')
def admin_dashboard(request):
    if not request.user.is_authenticated:
        return redirect('/login')
    if not has_dashboard_access(request.user):
        for perm, url_name in (
            ('shop.view_product', 'admin_products'),
            ('shop.view_catagory', 'admin_categories'),
            ('shop.view_order', 'admin_orders'),
            ('shop.view_payment', 'admin_payments'),
            ('shop.view_productrating', 'admin_reviews'),
            ('shop.change_product', 'low_stock'),
            ('shop.change_notification', 'admin_send_announcement'),
        ):
            if request.user.has_perm(perm):
                return redirect(url_name)
        return render(request, 'shop/admin/no_access.html', status=403)
    total_products = Product.objects.count()
    total_categories = Catagory.objects.count()
    total_orders = Order.objects.count()
    total_processing_revenue = sum(
        o.total_amount for o in Order.objects.filter(status='Processing')
    )
    total_shipped_revenue = sum(
        o.total_amount for o in Order.objects.filter(status='Shipped')
    )
    total_delivered_revenue = sum(
        o.total_amount for o in Order.objects.filter(status='Delivered')
    )
    total_all_revenue = sum(o.total_amount for o in Order.objects.all())
    pending_count = Order.objects.filter(status='Pending').count()

    # Revenue trend: last 6 months (excludes Cancelled orders)
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

    # Intraday revenue: today, hour by hour (excludes Cancelled orders)
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
    hour_labels = [f"{h:02d}:00" for h in range(24)]
    hour_revenue_values = [hourly_revenue[h] for h in range(24)]
    hour_count_values = [hourly_count[h] for h in range(24)]

    return render(request, 'shop/admin/dashboard.html', {
        'total_products': total_products,
        'total_categories': total_categories,
        'total_orders': total_orders,
        'total_processing_revenue': total_processing_revenue,
        'total_shipped_revenue': total_shipped_revenue,
        'total_delivered_revenue': total_delivered_revenue,
        'total_all_revenue': total_all_revenue,
        'pending_count': pending_count,
        'revenue_month_labels': json.dumps(revenue_month_labels),
        'revenue_month_values': json.dumps(revenue_month_values),
        'hour_labels': json.dumps(hour_labels),
        'hour_revenue_values': json.dumps(hour_revenue_values),
        'hour_count_values': json.dumps(hour_count_values),
        'today_label': timezone.localtime().strftime('%d %b %Y'),
    })


@staff_perm('shop.view_product')
def admin_products(request):
    q = request.GET.get('q', '').strip()
    products = Product.objects.select_related('category').all().order_by('-created_at')
    if q:
        products = products.filter(
            models.Q(name__icontains=q) |
            models.Q(category__name__icontains=q) |
            models.Q(vendor__icontains=q)
        )
    return render(request, 'shop/admin/products_list.html', {'products': products, 'query': q})


@staff_perm('shop.view_product')
def admin_products_rows(request):
    q = request.GET.get('q', '').strip()
    products = Product.objects.select_related('category').all().order_by('-created_at')
    if q:
        products = products.filter(
            models.Q(name__icontains=q) |
            models.Q(category__name__icontains=q) |
            models.Q(vendor__icontains=q)
        )
    html = render_to_string('shop/admin/partials/product_rows.html', {'products': products, 'query': q}, request=request)
    return JsonResponse({'rows': html, 'count': products.count()})


@staff_perm('shop.add_product')
def admin_product_add(request):
    categories = Catagory.objects.all()
    if request.method == 'POST':
        name = request.POST.get('name')
        vendor = request.POST.get('vendor')
        category_id = request.POST.get('category')
        quantity = request.POST.get('quantity')
        original_price = request.POST.get('original_price')
        selling_price = request.POST.get('selling_price')
        description = request.POST.get('description')
        status = 0 if request.POST.get('status') == 'on' else 1
        trending = request.POST.get('trending') == 'on'
        cash_on_delivery = request.POST.get('cash_on_delivery') == 'on'
        image = optimize_image(request.FILES.get('product_image'))
        details = {f: request.POST.get(f, '').strip() for f in
                   ['highlight_1', 'highlight_2', 'highlight_3',
                    'perk_1_title', 'perk_1_sub',
                    'perk_2_title', 'perk_2_sub',
                    'perk_3_title', 'perk_3_sub']}

        if not all([name, vendor, category_id, quantity, original_price, selling_price, description]):
            messages.error(request, "All required fields must be filled.")
            return render(request, 'shop/admin/product_form.html', {'categories': categories})

        try:
            category = Catagory.objects.get(id=category_id)
            product = Product.objects.create(
                category=category, name=name, vendor=vendor, quantity=int(quantity),
                original_price=float(original_price), selling_price=float(selling_price),
                description=description, status=status, trending=trending,
                cash_on_delivery=cash_on_delivery,
                product_image=image, **details,
            )
            for f in request.FILES.getlist('extra_images'):
                ProductImage.objects.create(product=product, image=optimize_image(f))
            messages.success(request, f"Product '{name}' added successfully.")
            return redirect('admin_products')
        except Exception as e:
            messages.error(request, f"Error: {e}")

    return render(request, 'shop/admin/product_form.html', {'categories': categories})


@staff_perm('shop.change_product')
def admin_product_edit(request, pid):
    product = get_object_or_404(Product, id=pid)
    categories = Catagory.objects.all()
    if request.method == 'POST':
        old_qty = product.quantity
        old_price = product.selling_price
        product.name = request.POST.get('name')
        product.vendor = request.POST.get('vendor')
        product.category_id = request.POST.get('category')
        product.quantity = int(request.POST.get('quantity'))
        product.original_price = float(request.POST.get('original_price'))
        product.selling_price = float(request.POST.get('selling_price'))
        product.description = request.POST.get('description')
        product.status = 0 if request.POST.get('status') == 'on' else 1
        product.trending = request.POST.get('trending') == 'on'
        product.cash_on_delivery = request.POST.get('cash_on_delivery') == 'on'
        for f in ['highlight_1', 'highlight_2', 'highlight_3',
                  'perk_1_title', 'perk_1_sub',
                  'perk_2_title', 'perk_2_sub',
                  'perk_3_title', 'perk_3_sub']:
            setattr(product, f, request.POST.get(f, '').strip())
        if request.FILES.get('product_image'):
            product.product_image = optimize_image(request.FILES['product_image'])
        elif request.POST.get('delete_cover') and product.product_image:
            product.product_image.delete(save=False)
            product.product_image = None
        for img in list(product.images.all()):
            if request.POST.get(f'delete_image_{img.id}'):
                img.delete()
        for f in request.FILES.getlist('extra_images'):
            ProductImage.objects.create(product=product, image=optimize_image(f))
        product.save()
        if old_qty <= 0 and product.quantity > 0:
            notify_product_back_in_stock(product)
        if product.selling_price < old_price:
            notify_product_price_drop(product, old_price, product.selling_price)
        messages.success(request, f"Product '{product.name}' updated.")
        return redirect('admin_products')
    return render(request, 'shop/admin/product_form.html', {'product': product, 'categories': categories})


@staff_perm('shop.delete_product')
def admin_product_delete(request, pid):
    product = get_object_or_404(Product, id=pid)
    name = product.name
    image_names = collect_product_images(product)
    product.delete()
    for image_name in image_names:
        delete_image_file(image_name)
    messages.success(request, f"Product '{name}' deleted.")
    return redirect('admin_products')


@staff_perm('shop.view_catagory')
def admin_categories(request):
    q = request.GET.get('q', '').strip()
    categories = Catagory.objects.all().order_by('-created_at')
    if q:
        categories = categories.filter(name__icontains=q)
    return render(request, 'shop/admin/categories_list.html', {'categories': categories, 'query': q})


@staff_perm('shop.view_catagory')
def admin_categories_rows(request):
    q = request.GET.get('q', '').strip()
    categories = Catagory.objects.all().order_by('-created_at')
    if q:
        categories = categories.filter(name__icontains=q)
    html = render_to_string('shop/admin/partials/category_rows.html', {'categories': categories, 'query': q}, request=request)
    return JsonResponse({'rows': html, 'count': categories.count()})


@staff_perm('shop.add_catagory')
def admin_category_add(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        description = request.POST.get('description')
        status = request.POST.get('status') == 'on'
        image = optimize_image(request.FILES.get('image'))
        if not name or not description:
            messages.error(request, "Name and description are required.")
            return render(request, 'shop/admin/category_form.html')
        try:
            Catagory.objects.create(name=name, description=description, status=status, image=image)
            messages.success(request, f"Category '{name}' added.")
            return redirect('admin_categories')
        except Exception as e:
            messages.error(request, f"Error: {e}")
    return render(request, 'shop/admin/category_form.html')


@staff_perm('shop.change_catagory')
def admin_category_edit(request, cid):
    category = get_object_or_404(Catagory, id=cid)
    if request.method == 'POST':
        category.name = request.POST.get('name')
        category.description = request.POST.get('description')
        category.status = request.POST.get('status') == 'on'
        if request.FILES.get('image'):
            category.image = optimize_image(request.FILES['image'])
        elif request.POST.get('delete_image'):
            category.image = None
        category.save()
        messages.success(request, f"Category '{category.name}' updated.")
        return redirect('admin_categories')
    return render(request, 'shop/admin/category_form.html', {'category': category})


@staff_perm('shop.delete_catagory')
def admin_category_delete(request, cid):
    category = get_object_or_404(Catagory, id=cid)
    name = category.name
    image_name = category.image.name if category.image else None
    category.delete()
    if image_name:
        delete_image_file(image_name)
    messages.success(request, f"Category '{name}' deleted.")
    return redirect('admin_categories')


@staff_perm('shop.view_order')
def admin_orders(request):
    q = request.GET.get('q', '').strip()
    orders = Order.objects.select_related('user').all().order_by('-created_at')
    if q:
        orders = orders.filter(
            models.Q(id__icontains=q) |
            models.Q(user__username__icontains=q) |
            models.Q(phone__icontains=q) |
            models.Q(status__icontains=q)
        )
    return render(request, 'shop/admin/orders_list.html', {'orders': orders, 'query': q})


@staff_perm('shop.view_order')
def admin_orders_rows(request):
    q = request.GET.get('q', '').strip()
    orders = Order.objects.select_related('user').all().order_by('-created_at')
    if q:
        orders = orders.filter(
            models.Q(id__icontains=q) |
            models.Q(user__username__icontains=q) |
            models.Q(phone__icontains=q) |
            models.Q(status__icontains=q)
        )
    html = render_to_string('shop/admin/partials/order_rows.html', {'orders': orders, 'query': q}, request=request)
    return JsonResponse({'rows': html, 'count': orders.count()})


@staff_perm('shop.view_order')
def admin_order_detail(request, oid):
    order = get_object_or_404(Order.objects.select_related('user').prefetch_related('items__product'), id=oid)
    return render(request, 'shop/admin/order_detail.html', {'order': order, 'ORDER_STATUS': ORDER_STATUS})


@staff_perm('shop.change_order')
def admin_order_status(request, oid):
    order = get_object_or_404(Order, id=oid)
    if request.method == 'POST':
        if order.status == 'Cancelled' and order.cancel_reason:
            messages.error(request, f"Order #{order.id} was cancelled by the user and its status cannot be changed.")
        else:
            new_status = request.POST.get('status')
            if new_status in dict(ORDER_STATUS):
                old_status = order.status
                order.status = new_status
                order.save()
                if old_status != new_status:
                    if new_status == 'Processing':
                        notify_order_confirmed(order.user, order)
                    elif new_status == 'Shipped':
                        notify_order_shipped(order.user, order)
                    elif new_status == 'Delivered':
                        notify_order_delivered(order.user, order)
                        generate_invoice_for_order(order)
                    elif new_status == 'Cancelled':
                        notify_order_cancelled(order.user, order)
                messages.success(request, f"Order #{order.id} status updated to '{new_status}'.")
            else:
                messages.error(request, "Invalid status.")
    return redirect('admin_order_detail', oid=oid)


def _admin_reviews_qs(q='', rating=''):
    reviews = ProductRating.objects.select_related('product', 'user').order_by('-created_at')
    if q:
        reviews = reviews.filter(
            models.Q(product__name__icontains=q) |
            models.Q(user__username__icontains=q) |
            models.Q(user__email__icontains=q) |
            models.Q(comment__icontains=q)
        )
    if rating:
        reviews = reviews.filter(rating=rating)
    return reviews


@staff_perm('shop.view_productrating')
def admin_reviews(request):
    q = request.GET.get('q', '').strip()
    rating = request.GET.get('rating', '').strip()
    reviews = _admin_reviews_qs(q, rating)
    return render(request, 'shop/admin/reviews_list.html', {
        'reviews': reviews,
        'query': q,
        'rating_filter': rating,
    })


@staff_perm('shop.view_productrating')
def admin_reviews_rows(request):
    q = request.GET.get('q', '').strip()
    rating = request.GET.get('rating', '').strip()
    reviews = _admin_reviews_qs(q, rating)
    html = render_to_string('shop/admin/partials/review_rows.html', {
        'reviews': reviews,
        'query': q,
        'rating_filter': rating,
    }, request=request)
    return JsonResponse({'rows': html, 'count': reviews.count()})


@staff_perm('shop.change_productrating')
def admin_review_edit(request, rid):
    review = get_object_or_404(ProductRating, id=rid)
    if request.method == 'POST':
        rating = request.POST.get('rating', '').strip()
        comment = request.POST.get('comment', '').strip()
        if rating not in ('1', '2', '3', '4', '5'):
            messages.error(request, 'Rating must be between 1 and 5.')
            return redirect('admin_review_edit', rid=rid)
        review.rating = int(rating)
        review.comment = comment[:500]
        image = request.FILES.get('image')
        remove_image = request.POST.get('remove_image') == 'on'
        old_name = review.image.name if review.image else ''
        if image:
            review.image = image
        elif remove_image and old_name:
            review.image = None
        review.save()
        if old_name and (image or remove_image):
            delete_image_file(old_name)
        messages.success(request, f"Review by {review.user.username} updated.")
        return redirect('admin_reviews')
    return render(request, 'shop/admin/review_form.html', {'review': review})


@staff_perm('shop.delete_productrating')
def admin_review_delete(request, rid):
    review = get_object_or_404(ProductRating, id=rid)
    image = review.image
    media = list(review.media.all())
    user_name = review.user.username
    review.delete()
    if image:
        delete_image_file(image)
    for m in media:
        delete_image_file(m.file)
    messages.success(request, f"Review by {user_name} deleted.")
    return redirect('admin_reviews')


def _admin_payments_qs(q='', status=''):
    payments = Payment.objects.select_related('user', 'order').order_by('-created_at')
    if q:
        payments = payments.filter(
            models.Q(user__username__icontains=q) |
            models.Q(user__email__icontains=q) |
            models.Q(order__id__icontains=q) |
            models.Q(razorpay_order_id__icontains=q)
        )
    if status:
        payments = payments.filter(status=status)
    return payments


@staff_perm('shop.view_payment')
def admin_payments(request):
    q = request.GET.get('q', '').strip()
    status = request.GET.get('status', '').strip()
    payments = _admin_payments_qs(q, status)
    return render(request, 'shop/admin/payments_list.html', {
        'payments': payments,
        'query': q,
        'status_filter': status,
    })


@staff_perm('shop.view_payment')
def admin_payments_rows(request):
    q = request.GET.get('q', '').strip()
    status = request.GET.get('status', '').strip()
    payments = _admin_payments_qs(q, status)
    html = render_to_string('shop/admin/partials/payment_rows.html', {
        'payments': payments,
        'query': q,
        'status_filter': status,
    }, request=request)
    return JsonResponse({'rows': html, 'count': payments.count()})


@staff_perm('shop.view_product')
def admin_products_autocomplete(request):
    q = request.GET.get('q', '').strip()
    if not q:
        return JsonResponse([], safe=False)
    products = Product.objects.filter(
        models.Q(name__icontains=q) |
        models.Q(vendor__icontains=q)
    )[:10]
    data = [{
        'id': p.id,
        'name': p.name,
        'vendor': p.vendor,
        'stock': p.quantity,
        'image': p.product_image.url if p.product_image else '',
    } for p in products]
    return JsonResponse(data, safe=False)


@staff_perm('shop.view_catagory')
def admin_categories_autocomplete(request):
    q = request.GET.get('q', '').strip()
    if not q:
        return JsonResponse([], safe=False)
    categories = Catagory.objects.filter(
        models.Q(name__icontains=q) |
        models.Q(description__icontains=q)
    )[:10]
    data = [{
        'id': c.id,
        'name': c.name,
        'description': c.description,
        'image': c.image.url if c.image else '',
    } for c in categories]
    return JsonResponse(data, safe=False)


ADMIN_SECTION_PERMS = {
    'products': ('view_product', 'add_product', 'change_product', 'delete_product'),
    'categories': ('view_catagory', 'add_catagory', 'change_catagory', 'delete_catagory'),
    'orders': ('view_order', 'change_order'),
    'payments': ('view_payment',),
    'reviews': ('view_productrating', 'change_productrating', 'delete_productrating'),
    'low_stock': ('change_product',),
    'send_announcement': ('change_notification',),
}


def admin_staff_permissions(request):
    if not request.user.is_authenticated:
        return redirect('/login')
    if not request.user.is_superuser:
        messages.error(request, "Only the superuser can manage staff permissions.")
        return redirect('admin_dashboard')

    staff_users = User.objects.filter(
        models.Q(is_staff=True) | models.Q(user_permissions__content_type__app_label='shop')
    ).distinct().order_by('username')

    if request.method == 'POST':
        for u in staff_users:
            if u.is_superuser:
                continue
            dash = request.POST.get('section_%d_dashboard' % u.id) == 'on'
            section_values = {
                key: request.POST.get('section_%d_%s' % (u.id, key)) == 'on'
                for key in ADMIN_SECTION_PERMS
            }
            any_granted = dash or any(section_values.values())
            if any_granted and not u.is_staff:
                u.is_staff = True
                u.save(update_fields=['is_staff'])
            profile, _ = UserProfile.objects.get_or_create(user=u)
            if profile.dashboard_access != dash:
                profile.dashboard_access = dash
                profile.save(update_fields=['dashboard_access'])
            wanted = {
                codename
                for key, codenames in ADMIN_SECTION_PERMS.items()
                if section_values[key]
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
                    u.user_permissions.add(perm)
                else:
                    u.user_permissions.remove(perm)
            messages.success(request, f"Permissions updated for {u.username}.")
        return redirect('admin_staff_permissions')

    perms_by_user = {}
    profiles = {p.user_id: p for p in UserProfile.objects.filter(user__in=staff_users)}
    for u in staff_users:
        codes = set(u.user_permissions.filter(content_type__app_label='shop').values_list('codename', flat=True))
        perms_by_user[u.id] = codes
    rows = [{
        'user': u,
        'dashboard': u.is_superuser or bool(profiles.get(u.id) and profiles[u.id].dashboard_access),
        'products': 'view_product' in perms_by_user.get(u.id, set()),
        'categories': 'view_catagory' in perms_by_user.get(u.id, set()),
        'orders': 'view_order' in perms_by_user.get(u.id, set()),
        'payments': 'view_payment' in perms_by_user.get(u.id, set()),
        'reviews': 'view_productrating' in perms_by_user.get(u.id, set()),
        'low_stock': 'change_product' in perms_by_user.get(u.id, set()),
        'send_announcement': 'change_notification' in perms_by_user.get(u.id, set()),
    } for u in staff_users]
    return render(request, 'shop/admin/staff_permissions.html', {'rows': rows})


_PINCODE_RE = re.compile(r'\b[1-9][0-9]{5}\b')


def _extract_pincode(*values):
    """Return a validated 6-digit Indian pincode found in the given values, or ''.

    Pass dedicated postal-code fields first (postcode/postal_code/zip/...); the
    remaining values are only scanned for an embedded pincode when no earlier
    value contains one. Whitespace is stripped before matching so formatting such
    as '600 001' or '600001 ' is still accepted. A match must be exactly 6
    consecutive digits and cannot start with 0 (Indian PIN zones are 1-9).
    """
    for value in values:
        if value is None:
            continue
        compact = re.sub(r'\s+', '', str(value))
        match = _PINCODE_RE.search(compact)
        if match:
            return match.group(0)
    return ''


_COUNTRY_NAMES = {'india', 'republic of india', 'bharat'}


def _pincode_from_display_name(display_name):
    """Return the pincode token that corresponds to the address tail.

    Nominatim display_name ends with '..., <postcode>, <country>', so the
    pincode sits immediately before the country name. Only the tail tokens are
    inspected (never the house-number/street prefix), so a stray 6-digit number
    earlier in the address cannot be picked up.
    """
    if not display_name:
        return ''
    parts = [p.strip() for p in str(display_name).split(',')]
    parts = [p for p in parts if p]
    if not parts:
        return ''
    if parts[-1].lower() in _COUNTRY_NAMES:
        parts = parts[:-1]
    for part in reversed(parts[-3:]):
        pin = _extract_pincode(part)
        if pin:
            return pin
    return ''


def google_reverse_geocode(lat, lng):
    key = getattr(settings, 'GOOGLE_MAPS_API_KEY', '')
    if not key:
        return None
    url = 'https://maps.googleapis.com/maps/api/geocode/json?' + urllib.parse.urlencode({
        'latlng': f'{lat},{lng}',
        'key': key,
        'language': 'en',
    })
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'KaviBazaar/1.0'})
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        if data.get('status') != 'OK' or not data.get('results'):
            logger.warning(f"Google geocoding status: {data.get('status')}")
            return None
        result = data['results'][0]
        ac = {}
        for comp in result.get('address_components', []):
            for t in comp.get('types', []):
                ac.setdefault(t, comp.get('long_name', ''))
        street = ', '.join(p for p in [ac.get('street_number'), ac.get('route')] if p)
        locality = (
            ac.get('sublocality_level_1') or ac.get('sublocality_level_2') or
            ac.get('locality') or ac.get('administrative_area_level_2') or ''
        )
        pincode = _extract_pincode(ac.get('postal_code'), ac.get('postal_code_suffix'))
        return {
            'pincode': pincode,
            'locality': locality,
            'address': street,
            'landmark': ac.get('point_of_interest', ''),
            'city': ac.get('locality') or ac.get('administrative_area_level_3', '') or '',
            'district': ac.get('administrative_area_level_2', ''),
            'state': ac.get('administrative_area_level_1', ''),
            'country': ac.get('country', ''),
            'display_name': result.get('formatted_address', ''),
            'source': 'google',
        }
    except Exception as e:
        logger.warning(f"Google geocoding failed: {e}")
        return None


def _nominatim_reverse(lat, lng):
    """Reverse-geocode via Nominatim and return the parsed address dict (or None)."""
    params = urllib.parse.urlencode({
        'format': 'jsonv2',
        'lat': lat,
        'lon': lng,
        'addressdetails': 1,
        'accept-language': 'en',
    })
    url = 'https://nominatim.openstreetmap.org/reverse?' + params
    req = urllib.request.Request(url, headers={
        'User-Agent': 'KaviBazaar/1.0 (ecommerce checkout)',
        'Accept': 'application/json',
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        logger.warning(f"Reverse geocode failed: {e}")
        return None
    if not data or not data.get('address'):
        return None

    a = data.get('address', {})
    address_parts = []
    if a.get('house_number'):
        address_parts.append(a['house_number'])
    if a.get('road'):
        address_parts.append(a['road'])
    street = ', '.join(address_parts)

    locality = (
        a.get('suburb') or a.get('neighbourhood') or a.get('residential') or
        a.get('town') or a.get('city_district') or a.get('city') or a.get('village') or ''
    )
    state = a.get('state', '')
    district = a.get('state_district', '') or a.get('county', '')
    if not locality:
        locality = district or state

    return {
        'locality': locality,
        'address': street,
        'landmark': a.get('amenity', ''),
        'city': a.get('city') or a.get('town') or a.get('village') or a.get('municipality') or '',
        'district': district,
        'state': state,
        'country': a.get('country', ''),
        'display_name': data.get('display_name', ''),
        'pincode': _extract_pincode(
            a.get('postcode'), a.get('postal_code'), a.get('postalcode'),
            a.get('zip'), a.get('zipcode'),
        ) or _pincode_from_display_name(data.get('display_name', '')),
    }


def _resolve_pincode(nom, lat, lng):
    """Return the validated pincode from the reverse-geocoding response, or ''.

    Nominatim's structured `postcode` field (or the postcode token at the end of
    its display_name) corresponds to the resolved address/locality and is used
    as-is. Only when that is absent do we ask BigDataCloud for a postcode at the
    same coordinate. The pincode is never derived from city/district/state names.
    """
    pin = (nom or {}).get('pincode') or ''
    if pin:
        return pin
    return get_pincode_fallback(
        lat, lng, (nom or {}).get('locality', ''), (nom or {}).get('state', ''),
        (nom or {}).get('district', ''),
    )


def reverse_geocode(request):
    lat = request.GET.get('lat', '').strip()
    lng = request.GET.get('lng', '').strip()
    if not lat or not lng:
        return JsonResponse({'error': 'Missing lat/lng'}, status=400)

    accuracy = request.GET.get('accuracy', '').strip()
    if accuracy:
        logger.info(f"Reverse geocode request accuracy={accuracy} m")

    try:
        lat = float(lat)
        lng = float(lng)
    except ValueError:
        return JsonResponse({'error': 'Invalid coordinates'}, status=400)

    google_result = google_reverse_geocode(lat, lng)
    if google_result is not None:
        if not google_result.get('pincode'):
            google_result['pincode'] = _resolve_pincode(_nominatim_reverse(lat, lng), lat, lng)
        return JsonResponse(google_result)

    nom = _nominatim_reverse(lat, lng)
    if nom is None:
        return JsonResponse({'error': 'Geocoding service unavailable'}, status=502)

    nom['pincode'] = _resolve_pincode(nom, lat, lng)
    return JsonResponse(nom)


def nearby_landmark(request):
    lat = request.GET.get('lat', '').strip()
    lng = request.GET.get('lng', '').strip()
    if not lat or not lng:
        return JsonResponse({'error': 'Missing lat/lng'}, status=400)
    try:
        lat = float(lat)
        lng = float(lng)
    except ValueError:
        return JsonResponse({'error': 'Invalid coordinates'}, status=400)
    return JsonResponse({'landmark': get_nearby_landmark(lat, lng)})


def get_pincode_fallback(lat, lng, locality, state, district=''):
    """Return a postcode for these exact coordinates from a geocoding service only.

    The pincode is never derived from locality/city/state names. BigDataCloud maps
    the exact coordinate to a postcode; if it returns no postcode we return '' so
    the caller leaves the pincode field empty rather than guessing.
    """
    try:
        url = (
            'https://api.bigdatacloud.net/data/reverse-geocode-client'
            '?latitude={lat}&longitude={lng}&localityLanguage=en'
        ).format(lat=lat, lng=lng)
        req = urllib.request.Request(url, headers={'User-Agent': 'KaviBazaar/1.0'})
        with urllib.request.urlopen(req, timeout=12) as resp:
            d = json.loads(resp.read().decode('utf-8'))
        return _extract_pincode(
            d.get('postcode'), d.get('postalCode'), d.get('postal_code'),
            d.get('zip'), d.get('zipcode'),
        )
    except Exception as e:
        logger.warning(f"BigDataCloud pincode lookup failed: {e}")
        return ''


def get_nearby_landmark(lat, lng):
    photon_url = (
        'https://photon.komoot.io/reverse?lon={lng}&lat={lat}&limit=6'
    ).format(lat=lat, lng=lng)
    try:
        req = urllib.request.Request(photon_url, headers={
            'User-Agent': 'KaviBazaar/1.0 (ecommerce checkout)',
        })
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        for feature in data.get('features', []):
            props = feature.get('properties', {})
            name = props.get('name', '')
            if not name:
                continue
            if props.get('osm_key') == 'highway' or props.get('type') == 'street':
                continue
            return name
    except Exception as e:
        logger.warning(f"Nearby landmark lookup failed on photon: {e}")

    query = (
        '[out:json][timeout:10];'
        '('
        '  node["amenity"]["name"](around:300,{lat},{lng});'
        '  way["amenity"]["name"](around:300,{lat},{lng});'
        ');'
        'out 1;'
    ).format(lat=lat, lng=lng)
    body = 'data=' + urllib.parse.quote(query)
    mirrors = [
        'https://overpass-api.de/api/interpreter',
        'https://overpass.kumi.systems/api/interpreter',
        'https://overpass.private.coffee/api/interpreter',
    ]
    for url in mirrors:
        req = urllib.request.Request(url, data=body.encode('utf-8'), headers={
            'User-Agent': 'KaviBazaar/1.0 (ecommerce checkout)',
        })
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode('utf-8'))
            elements = data.get('elements', [])
            if elements:
                name = elements[0].get('tags', {}).get('name', '')
                if name:
                    return name
            break
        except Exception as e:
            logger.warning(f"Nearby landmark lookup failed on {url}: {e}")
            continue
    return ''