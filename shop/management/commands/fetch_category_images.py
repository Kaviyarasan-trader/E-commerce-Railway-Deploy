import html, time
from difflib import SequenceMatcher
from bs4 import BeautifulSoup
import requests
from django.core.management.base import BaseCommand
from django.core.files.base import ContentFile
from shop.models import Catagory

search_headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
}

KEEP = ['Mobiles', 'Shirts For Men', 'Pants For Men', 'Cloths For Ladies', 'Electronics']

TERMS = {
    'Home & Kitchen': 'kitchen mixer',
    'Sports & Fitness': 'dumbbells',
    'Books & Stationery': 'notebook',
    'Beauty & Personal Care': 'lipstick',
    'Footwear': 'sneakers',
    'Watches': 'wrist watch',
    'Bags & Luggage': 'laptop bag',
    'Jewellery': 'gold ring',
    'Toys & Baby': 'teddy bear',
    'Grocery & Snacks': 'potato chips',
    'Furniture': 'sofa',
    'Automotive Accessories': 'car seat cover',
    'Pet Supplies': 'dog food',
    'Health & Wellness': 'bp monitor',
    'Office Supplies': 'sketch pen',
    'Garden & Outdoor': 'garden tools',
    'Musical Instruments': 'guitar',
    'Cameras & Photography': 'dslr camera',
    'Video Games & Consoles': 'gaming controller',
    'Travel & Adventure': 'travel bag',
}


def similar(a, b):
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def search_flipkart(term):
    try:
        url = f'https://www.flipkart.com/search?q={term}'
        r = requests.get(url, headers=search_headers, timeout=15)
        soup = BeautifulSoup(r.text, 'lxml')
        results = []
        for img in soup.find_all('img'):
            src = img.get('src') or img.get('data-src') or ''
            alt = img.get('alt', '').strip()
            if 'rukminim2' in src and alt:
                src = src.replace('/612/612/', '/832/832/')
                results.append((html.unescape(alt), src))
                if len(results) >= 15:
                    break
        return results
    except Exception:
        return None


def download_image(url):
    try:
        r = requests.get(url, timeout=15, headers=search_headers)
        if r.status_code == 200 and len(r.content) > 1000:
            return ContentFile(r.content)
    except Exception:
        pass
    return None


class Command(BaseCommand):
    help = 'Fetch a clean Flipkart product image for each category page'

    def add_arguments(self, parser):
        parser.add_argument('--all', action='store_true',
                            help='Also update the first 4 + Electronics categories')

    def handle(self, *args, **options):
        cats = list(Catagory.objects.filter(status=0))
        targets = cats if options.get('all') else [c for c in cats if c.name not in KEEP]
        self.stdout.write(f'Fetching Flipkart images for {len(targets)} categories...')

        updated = 0
        failed = 0
        for cat in targets:
            term = TERMS.get(cat.name)
            if not term:
                continue
            results = search_flipkart(term)
            if not results:
                self.stdout.write(self.style.WARNING(f'  NO RESULTS: {cat.name}'))
                failed += 1
                continue
            best_score, best_url, best_alt = 0, None, None
            for alt, src in results:
                score = similar(term, alt)
                if score > best_score:
                    best_score, best_url, best_alt = score, src, alt
            img = download_image(best_url) if best_url else None
            if img:
                cat.image.save(f'category_{cat.id}.jpg', img, save=True)
                updated += 1
                self.stdout.write(f'  OK: {cat.name} <- "{best_alt[:60]}" ({best_score:.2f})')
            else:
                self.stdout.write(self.style.ERROR(f'  DOWNLOAD FAIL: {cat.name}'))
                failed += 1
            time.sleep(1)

        self.stdout.write(self.style.SUCCESS(
            f'Done! Updated {updated} categories; {failed} failed.'
        ))
