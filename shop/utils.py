import os
from io import BytesIO

from PIL import Image
from django.core.files.uploadedfile import InMemoryUploadedFile


def delete_image_file(field_or_name, exclude=None):
    """Delete an uploaded image file from the media folder.

    Files are stored under MEDIA_ROOT/<subfolder> (e.g. 'uploads/<name>' or
    'ratings/<name>'), so remove the file there. STATIC_ROOT is also checked
    in case a stale collected copy exists. The file is only removed if no
    other DB row still references it (uploads can be shared after duplicate
    cleanup). Pass the model instance being changed as ``exclude`` so its own
    (about-to-be-replaced) field is ignored during pre-save cleanup.
    """
    from django.conf import settings

    name = getattr(field_or_name, 'name', field_or_name) or ''
    if not name:
        return
    name = str(name).replace('\\', '/')
    base = os.path.basename(name)
    if _is_image_referenced(name, exclude=exclude):
        return
    folder = os.path.dirname(name) or 'uploads'
    for root in (settings.MEDIA_ROOT, settings.STATIC_ROOT):
        if not root:
            continue
        try:
            target = os.path.join(str(root), folder, base)
            if os.path.isfile(target):
                os.remove(target)
        except OSError:
            pass


def _is_image_referenced(name, exclude=None):
    """Return True if any remaining DB row still references this upload file."""
    from .models import Catagory, Product, ProductImage, UserProfile, ProductRating, ProductRatingMedia

    path = str(name).replace('\\', '/')
    base = os.path.basename(path)

    def ex(qs, model):
        if exclude is not None and isinstance(exclude, model):
            return qs.exclude(pk=exclude.pk)
        return qs

    return (
        ex(Product.objects, Product).filter(product_image=path).exists()
        or ex(ProductImage.objects, ProductImage).filter(image=path).exists()
        or ex(Catagory.objects, Catagory).filter(image=path).exists()
        or ex(UserProfile.objects, UserProfile).filter(profile_picture=path).exists()
        or ex(ProductRating.objects, ProductRating).filter(image=path).exists()
        or ex(ProductRating.objects, ProductRating).filter(image=f'uploads/{base}').exists()
        or ex(ProductRatingMedia.objects, ProductRatingMedia).filter(file=path).exists()
        or ex(ProductRatingMedia.objects, ProductRatingMedia).filter(file=f'uploads/{base}').exists()
    )


def collect_product_images(product):
    """Return the stored upload filenames for a product's cover + gallery images."""
    names = []
    if product.product_image:
        names.append(product.product_image.name)
    for img in product.images.all():
        if img.image:
            names.append(img.image.name)
    return names


def fetch_gravatar(email, size=400):
    """Download the Gravatar image for an email address.

    Returns an InMemoryUploadedFile ready to assign to a profile_picture
    field, or None when the email has no Gravatar (or on any failure). Since
    users log in with Gmail addresses, this usually matches their Google
    profile picture when a Gravatar is set up for that address.
    """
    import hashlib
    import urllib.request

    email = (email or '').strip().lower()
    if not email:
        return None
    digest = hashlib.md5(email.encode('utf-8')).hexdigest()
    url = f'https://www.gravatar.com/avatar/{digest}?s={size}&d=404&r=g'
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'KaviBazaar/1.0'})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = resp.read()
            if not data:
                return None
            ctype = resp.headers.get('Content-Type', 'image/png').split(';')[0].strip()
            ext = 'png' if 'png' in ctype else 'jpg'
            return InMemoryUploadedFile(
                BytesIO(data),
                'profile_picture',
                f'gravatar_{digest}.{ext}',
                ctype,
                len(data),
                None,
            )
    except Exception:
        return None


def fetch_google_picture(url):
    """Download the Google account profile picture URL from an ID token.

    Returns an InMemoryUploadedFile ready to assign to a profile_picture
    field, or None on any failure.
    """
    import urllib.request

    if not url:
        return None
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'KaviBazaar/1.0'})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = resp.read()
            if not data:
                return None
            ctype = resp.headers.get('Content-Type', 'image/png').split(';')[0].strip()
            ext = 'png' if 'png' in ctype else 'jpg'
            return InMemoryUploadedFile(
                BytesIO(data),
                'profile_picture',
                f'google_picture.{ext}',
                ctype,
                len(data),
                None,
            )
    except Exception:
        return None


def optimize_image(uploaded, max_size=900, quality=82):
    """Downscale + recompress an uploaded image so it loads fast on the site."""
    if not uploaded:
        return uploaded
    try:
        img = Image.open(uploaded)
        fmt = (img.format or 'JPEG').upper()
        if img.mode not in ('RGB', 'RGBA', 'LA'):
            img = img.convert('RGBA' if fmt == 'PNG' and img.mode in ('RGBA', 'P') else 'RGB')

        if img.width > max_size or img.height > max_size:
            img.thumbnail((max_size, max_size), Image.LANCZOS)

        buf = BytesIO()
        if fmt == 'PNG':
            if img.mode != 'RGBA':
                img = img.convert('RGBA')
            img.save(buf, format='PNG', optimize=True)
            ctype = 'image/png'
            ext = 'png'
        else:
            if img.mode != 'RGB':
                img = img.convert('RGB')
            img.save(buf, format='JPEG', quality=quality, optimize=True, progressive=True)
            ctype = 'image/jpeg'
            ext = 'jpg'

        name = (uploaded.name.rsplit('.', 1)[0] if uploaded.name else 'image') + '.' + ext
        buf.seek(0)
        return InMemoryUploadedFile(
            buf, uploaded.field_name, name, ctype, buf.getbuffer().nbytes, None
        )
    except Exception:
        return uploaded
