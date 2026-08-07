import io
from django.core.management.base import BaseCommand
from django.core.files.base import ContentFile
from PIL import Image, ImageDraw, ImageFont
from shop.models import Catagory

cat_colors = {
    'Mobiles': ((30, 60, 110), (60, 100, 180)),
    'Shirts For Men': ((30, 80, 60), (70, 150, 110)),
    'Pants For Men': ((60, 50, 90), (110, 90, 170)),
    'Cloths For Ladies': ((120, 40, 70), (200, 90, 130)),
    'Electronics': ((20, 70, 100), (60, 140, 190)),
    'Home & Kitchen': ((140, 70, 20), (220, 140, 70)),
    'Sports & Fitness': ((30, 100, 50), (80, 190, 120)),
    'Books & Stationery': ((80, 50, 30), (160, 110, 70)),
    'Beauty & Personal Care': ((140, 30, 60), (230, 90, 130)),
    'Footwear': ((40, 40, 60), (90, 90, 130)),
    'Watches': ((50, 50, 70), (120, 120, 160)),
    'Bags & Luggage': ((90, 55, 20), (170, 120, 60)),
    'Jewellery': ((110, 70, 15), (220, 160, 70)),
    'Toys & Baby': ((20, 80, 90), (70, 160, 180)),
    'Grocery & Snacks': ((30, 90, 45), (90, 200, 120)),
    'Furniture': ((90, 55, 30), (170, 120, 80)),
    'Automotive Accessories': ((50, 50, 60), (110, 110, 130)),
    'Pet Supplies': ((90, 70, 20), (190, 160, 70)),
    'Health & Wellness': ((20, 80, 60), (70, 180, 140)),
    'Office Supplies': ((50, 60, 90), (110, 130, 180)),
    'Garden & Outdoor': ((40, 90, 40), (100, 200, 100)),
    'Musical Instruments': ((70, 40, 80), (150, 100, 180)),
    'Cameras & Photography': ((60, 60, 70), (130, 130, 150)),
    'Video Games & Consoles': ((90, 30, 40), (190, 80, 100)),
    'Travel & Adventure': ((30, 70, 80), (80, 160, 180)),
}


def generate_category_placeholder(cat):
    base = cat_colors.get(cat.name, ((60, 52, 137), (107, 91, 214)))
    top, bottom = base
    img = Image.new('RGB', (600, 600))
    px = img.load()
    for y in range(600):
        t = y / 600
        r = int(top[0] + (bottom[0] - top[0]) * t)
        g = int(top[1] + (bottom[1] - top[1]) * t)
        b = int(top[2] + (bottom[2] - top[2]) * t)
        for x in range(600):
            px[x, y] = (r, g, b)

    draw = ImageDraw.Draw(img, 'RGBA')
    draw.ellipse((-120, -120, 320, 320), fill=(255, 255, 255, 26))
    draw.ellipse((420, 380, 720, 680), fill=(255, 255, 255, 20))

    try:
        font = ImageFont.truetype("arialbd.ttf", 44)
        font_s = ImageFont.truetype("arial.ttf", 20)
    except Exception:
        try:
            font = ImageFont.truetype("arial.ttf", 44)
            font_s = ImageFont.truetype("arial.ttf", 20)
        except Exception:
            font = ImageFont.load_default()
            font_s = font

    name = cat.name
    max_chars = 22
    if len(name) > max_chars:
        name = name[: max_chars - 3] + '...'

    for i, line in enumerate(name.split(' ')):
        bbox = draw.textbbox((0, 0), line, font=font)
        tw = bbox[2] - bbox[0]
        draw.text(((600 - tw) / 2, 210 + i * 62), line, fill=(255, 255, 255), font=font)

    tag = 'KAVIBAZAAR'
    bbox2 = draw.textbbox((0, 0), tag, font=font_s)
    tw2 = bbox2[2] - bbox2[0]
    draw.text(((600 - tw2) / 2, 400), tag, fill=(250, 199, 117), font=font_s)

    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=85)
    buf.seek(0)
    return ContentFile(buf.read())


class Command(BaseCommand):
    help = 'Generate branded placeholder images for categories without an image'

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true')

    def handle(self, *args, **options):
        cats = list(Catagory.objects.all() if options.get('force') else Catagory.objects.filter(image=''))
        if not cats:
            self.stdout.write('All categories already have images.')
            return

        done = 0
        for cat in cats:
            img = generate_category_placeholder(cat)
            fname = f'category_{cat.id}.jpg'
            cat.image.save(fname, img, save=True)
            done += 1
            self.stdout.write(f'  OK: {cat.name}')

        self.stdout.write(self.style.SUCCESS(f'Done! Generated {done} category image(s).'))
