import io, re, html, requests, concurrent.futures, time
from urllib.parse import quote
from difflib import SequenceMatcher
from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand
from django.core.files.base import ContentFile
from PIL import Image, ImageDraw, ImageFont
from shop.models import Product


search_headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
}


def similar(a, b):
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def search_flipkart(search_term, timeout=10):
    try:
        url = f'https://www.flipkart.com/search?q={quote(search_term)}'
        r = requests.get(url, headers=search_headers, timeout=timeout)
        soup = BeautifulSoup(r.text, 'lxml')
        results = []
        for img in soup.find_all('img'):
            src = img.get('src') or img.get('data-src') or ''
            alt = img.get('alt', '').strip()
            if 'rukminim2' in src and alt:
                results.append((html.unescape(alt), src.replace('?q=70', '?q=90')))
                if len(results) >= 15:
                    break
        return results
    except Exception:
        return None


def download_image(url, timeout=10):
    try:
        r = requests.get(url, timeout=timeout, headers=search_headers)
        if r.status_code == 200 and len(r.content) > 1000:
            return ContentFile(r.content)
    except Exception:
        pass
    return None


def is_placeholder(product):
    try:
        from PIL import Image as PILImage
        with PILImage.open(product.product_image.path) as im:
            return im.size == (400, 400)
    except Exception:
        return False


cat_colors = {
    'Mobiles': (30, 60, 110), 'Shirts For Men': (30, 80, 60),
    'Pants For Men': (60, 50, 90), 'Cloths For Ladies': (120, 40, 70),
    'Electronics': (20, 70, 100), 'Home & Kitchen': (140, 70, 20),
    'Sports & Fitness': (30, 100, 50), 'Books & Stationery': (80, 50, 30),
    'Beauty & Personal Care': (140, 30, 60),
}


def generate_placeholder(product):
    base = cat_colors.get(product.category.name if product.category else 'General', (80, 80, 80))
    bg = (min(base[0] + 30, 255), min(base[1] + 30, 255), min(base[2] + 30, 255))
    img = Image.new('RGB', (400, 400), bg)
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 24)
        font_s = ImageFont.truetype("arial.ttf", 18)
    except Exception:
        font = ImageFont.load_default()
        font_s = font
    short = product.name if len(product.name) <= 22 else product.name[:19] + '...'
    bbox = draw.textbbox((0, 0), short, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((400 - tw) / 2, (400 - th) / 2 - 15), short, fill=(255, 255, 255), font=font)
    price = f'Rs.{int(product.selling_price)}'
    bbox2 = draw.textbbox((0, 0), price, font=font_s)
    tw2, th2 = bbox2[2] - bbox2[0], bbox2[3] - bbox2[1]
    draw.text(((400 - tw2) / 2, (400 - th2) / 2 + 20), price, fill=(220, 220, 220), font=font_s)
    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=80)
    buf.seek(0)
    return ContentFile(buf.read())


def clean_search_term(name):
    s = re.sub(r'\(.*?\)', '', name)
    s = re.sub(r'[,\-]', ' ', s)
    s = ' '.join(s.split())
    return s


def process_product(product):
    search = clean_search_term(product.name)
    results = search_flipkart(search)
    best_score = 0
    best_url = None
    if results:
        for alt, src in results:
            score = similar(search, alt)
            if score > best_score:
                best_score = score
                best_url = src
    if best_url and best_score > 0.25:
        img = download_image(best_url)
        if img:
            fname = f'product_{product.id}.jpg'
            product.product_image.save(fname, img, save=True)
            return product.id, True, f'{product.name} -> {best_score:.2f}'
    return product.id, False, product.name


class Command(BaseCommand):
    help = 'Search Flipkart for product images, fallback to placeholders'

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true')
        parser.add_argument('--grouped', action='store_true',
                            help='Fetch one image per base product name and apply to all variants')
        parser.add_argument('--distinct', action='store_true',
                            help='Fetch distinct images for every variant of a base product')

    def distinct(self):
        products = list(Product.objects.filter(status=0).select_related('category'))
        groups = {}
        for p in products:
            base = p.name.split(' (')[0]
            groups.setdefault(base, []).append(p)
        groups = [g for g in groups.items() if len(g[1]) > 1]
        total = len(groups)
        self.stdout.write(f'Differentiating images for {total} multi-variant groups...')

        updated = 0
        for gi, (base, members) in enumerate(groups, 1):
            search_term = clean_search_term(base)
            results = search_flipkart(search_term)
            time.sleep(0.3)
            if not results:
                continue

            unique = []
            seen_src = set()
            for alt, src in results:
                if src not in seen_src:
                    seen_src.add(src)
                    unique.append((alt, src))
            if len(unique) < 2:
                continue

            candidates = {}
            def fetch(spec):
                alt, src = spec
                img = download_image(src)
                return alt, src, img
            with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
                fetched = list(ex.map(fetch, unique[:12]))
            downloaded = [(alt, src) for alt, src, img in fetched if img]

            if len(downloaded) < 2:
                continue

            scored = {}
            for m in members:
                mt = clean_search_term(m.name)
                scored[m.id] = sorted(
                    ((similar(mt, alt), src) for alt, src in downloaded),
                    key=lambda x: -x[0],
                )

            img_by_src = {src: img for alt, src, img in fetched if img}
            used = set()
            group_updated = 0
            for m in members:
                for score, src in scored[m.id]:
                    if src in used:
                        continue
                    fname = f'product_{m.id}.jpg'
                    m.product_image.save(fname, img_by_src[src], save=True)
                    updated += 1
                    used.add(src)
                    group_updated += 1
                    break
            self.stdout.write(f'  [{gi}/{total}] {base}: {len(members)} variants -> {group_updated} images')

        self.stdout.write(self.style.SUCCESS(
            f'Done! Updated {updated} products with distinct variant images.'
        ))

    def grouped(self):
        products = list(Product.objects.filter(status=0).select_related('category'))
        groups = {}
        for p in products:
            base = p.name.split(' (')[0]
            groups.setdefault(base, []).append(p)
        groups = sorted(groups.items(), key=lambda kv: -len(kv[1]))
        self.stdout.write(f'Checking {len(groups)} product groups...')

        updated = 0
        failed = 0
        skipped = 0
        for base, members in groups:
            if not any(is_placeholder(p) for p in members):
                skipped += 1
                continue
            search = clean_search_term(base)
            results = search_flipkart(search)
            best_score = 0
            best_url = None
            if results:
                for alt, src in results:
                    score = similar(search, alt)
                    if score > best_score:
                        best_score = score
                        best_url = src
            if best_url and best_score > 0.25:
                img = download_image(best_url)
                if img:
                    for p in members:
                        fname = f'product_{p.id}.jpg'
                        p.product_image.save(fname, img, save=True)
                    updated += len(members)
                    self.stdout.write(f'  OK ({len(members)}): {base} -> {best_score:.2f}')
                    time.sleep(1)
                    continue
            failed += 1
            self.stdout.write(f'  FAIL: {base}')
            time.sleep(1)

        self.stdout.write(self.style.SUCCESS(
            f'Done! Real images applied to {updated} products; {failed} groups kept placeholders; {skipped} already done.'
        ))

    def handle(self, *args, **options):
        if options.get('grouped'):
            self.grouped()
            return
        if options.get('distinct'):
            self.distinct()
            return

        if options.get('force'):
            products = list(Product.objects.all())
        else:
            products = list(Product.objects.filter(product_image=''))
        total = len(products)
        if total == 0:
            self.stdout.write('All products already have images.')
            return

        downloaded = 0
        failed = 0

        self.stdout.write(f'Searching Flipkart for {total} products...')
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
            futures = {ex.submit(process_product, p): p for p in products}
            for future in concurrent.futures.as_completed(futures):
                pid, ok, label = future.result()
                if ok:
                    downloaded += 1
                    self.stdout.write(f'  OK: {label}')
                else:
                    failed += 1
                    self.stdout.write(f'  FAIL: {label}')
                time.sleep(1)

        still_empty = list(Product.objects.filter(product_image=''))
        if still_empty:
            self.stdout.write(f'\nGenerating placeholders for {len(still_empty)} products...')
            for p in still_empty:
                img = generate_placeholder(p)
                fname = f'product_{p.id}.jpg'
                p.product_image.save(fname, img, save=True)

        self.stdout.write(self.style.SUCCESS(
            f'Done! Flipkart: {downloaded}, Placeholder: {len(still_empty)}'
        ))
