from django.core.management.base import BaseCommand
from shop.models import Catagory, Product


cat_products = {
    'Mobiles': [
        ('iPhone 16 Pro Max (Natural Titanium, 512 GB)', 'Apple', 159900, 149900, 10, True),
        ('Samsung Galaxy S25 Ultra (Titanium Gray, 512 GB)', 'Samsung', 134999, 124999, 8, True),
        ('OnePlus 13 (Arctic Dawn, 512 GB)', 'OnePlus', 69999, 64999, 12, True),
        ('Vivo X200 Pro (Blue, 512 GB)', 'Vivo', 89999, 84999, 7, True),
        ('Xiaomi 15 Pro (Black, 512 GB)', 'Xiaomi', 79999, 74999, 9, True),
        ('Nothing Phone 3 (White, 256 GB)', 'Nothing', 44999, 39999, 15, False),
        ('Motorola Edge 50 Ultra (Black, 512 GB)', 'Motorola', 59999, 54999, 6, False),
        ('Realme GT 7 Pro (Silver, 256 GB)', 'Realme', 49999, 44999, 11, True),
        ('iQOO 13 (Legend, 256 GB)', 'iQOO', 54999, 49999, 5, False),
        ('Asus Zenfone 12 (Black, 256 GB)', 'Asus', 69999, 64999, 4, False),
    ],
    'Shirts For Men': [
        ('US Polo Printed Cotton Shirt', 'US Polo', 1799, 799, 25, True),
        ('Arrow Regular Fit Formal Shirt', 'Arrow', 2199, 1099, 20, False),
        ('Van Heusen Slim Fit Shirt', 'Van Heusen', 1999, 899, 30, True),
        ('Peter England Casual Shirt', 'Peter England', 1499, 699, 22, False),
        ('Louis Philippe Premium Shirt', 'Louis Philippe', 2999, 1499, 15, True),
        ('Maniac Slim Fit Printed Shirt', 'Maniac', 1199, 499, 18, False),
        ('Roadster Linen Shirt', 'Roadster', 1599, 699, 28, True),
        ('HIGHLANDER Cotton Slim Shirt', 'HIGHLANDER', 999, 399, 35, False),
        ('The Indian Garage Co. Shirt', 'The Indian Garage Co.', 1349, 599, 20, True),
        ('Bonn Homme Oxford Shirt', 'Bonn Homme', 1899, 849, 12, False),
    ],
    'Pants For Men': [
        ('Levis 512 Slim Taper Jeans', 'Levis', 3299, 1999, 20, True),
        ('US Polo Chinos', 'US Polo', 2499, 1199, 18, False),
        ('Jack & Jones Slim Jeans', 'Jack & Jones', 2799, 1349, 22, True),
        ('Roadster Jogger Pants', 'Roadster', 1399, 699, 30, False),
        ('Peter England Trousers', 'Peter England', 1999, 949, 15, True),
        ('Dennis Lingo Jeans', 'Dennis Lingo', 2299, 1099, 25, False),
        ('HIGHLANDER Cargo Pants', 'HIGHLANDER', 1199, 549, 35, True),
        ('Mufti Regular Fit Jeans', 'Mufti', 2199, 999, 20, False),
        ('Bewakoof Joggers', 'Bewakoof', 1299, 649, 28, True),
        ('Spykar Slim Fit Jeans', 'Spykar', 2599, 1299, 16, False),
    ],
    'Cloths For Ladies': [
        ('V Calla Floral Midi Dress', 'V Calla', 2499, 1199, 10, True),
        ('Libas Printed Fit & Flare Dress', 'Libas', 1799, 849, 15, False),
        ('Indo Era Embroidery Dress', 'Indo Era', 2199, 999, 12, True),
        ('Soch Cotton Straight Dress', 'Soch', 2999, 1499, 8, False),
        ('Varanga A-Line Dress', 'Varanga', 1599, 749, 20, True),
        ('Fabindia Cotton Maxi Dress', 'Fabindia', 3499, 1899, 7, False),
        ('Anouk Embellished Dress', 'Anouk', 2599, 1299, 14, True),
        ('SASSAFras Bodycon Dress', 'SASSAFras', 1899, 899, 18, False),
        ('Miterra Wrap Dress', 'Miterra', 1399, 649, 22, True),
        ('Kurta Set with Dupatta', 'Biba', 2299, 1099, 16, False),
    ],
    'Electronics': [
        ('MacBook Air M4 (Silver, 256 GB)', 'Apple', 114900, 99900, 15, True),
        ('MacBook Pro 16 M4 Pro (Space Black, 512 GB)', 'Apple', 249900, 229900, 8, True),
        ('Dell XPS 16 (Platinum, 1 TB)', 'Dell', 189990, 169990, 6, False),
        ('HP Spectre x360 (Slate Blue, 512 GB)', 'HP', 149999, 129999, 10, True),
        ('Lenovo ThinkPad X1 Carbon (Black, 512 GB)', 'Lenovo', 179990, 159990, 5, False),
        ('iPad Pro M4 13-inch (Space Black, 256 GB)', 'Apple', 99900, 89900, 12, True),
        ('Samsung Galaxy Tab S10 Ultra (Gray, 256 GB)', 'Samsung', 89999, 79999, 8, False),
        ('Sony WH-1000XM6 Headphones (Black)', 'Sony', 29999, 24999, 20, True),
        ('Apple AirPods Pro 3 (USB-C)', 'Apple', 24900, 21900, 25, True),
        ('Samsung Galaxy Watch 7 (Silver, 44mm)', 'Samsung', 35999, 29999, 15, False),
    ],
    'Home & Kitchen': [
        ('Ninja Air Fryer Pro (5.5L)', 'Ninja', 12999, 8999, 12, True),
        ('Philips Instant Pot Duo (6L)', 'Philips', 9999, 7499, 10, False),
        ('KitchenAid Stand Mixer (Empire Red)', 'KitchenAid', 42999, 34999, 5, True),
        ('Prestige Induction Cooktop (2100W)', 'Prestige', 4999, 3499, 18, False),
        ('Bajaj Mixer Grinder (750W)', 'Bajaj', 3999, 2799, 22, True),
        ('Milton Thermosteel Flask (1L)', 'Milton', 1499, 899, 30, False),
        ('Godrej Refrigerator (260L, Frost Free)', 'Godrej', 34999, 29999, 7, True),
        ('LG Microwave Oven (32L, Convection)', 'LG', 21999, 17999, 9, False),
        ('Butterfly Electric Kettle (1.5L)', 'Butterfly', 1999, 1299, 25, True),
        ('Hawkins Pressure Cooker (5L)', 'Hawkins', 3499, 2499, 15, False),
    ],
    'Sports & Fitness': [
        ('Nike Air Zoom Pegasus 41 (Running Shoes)', 'Nike', 14995, 9995, 20, True),
        ('Adidas Ultraboost Light (Running Shoes)', 'Adidas', 17999, 11999, 15, False),
        ('Cult Fit Home Gym Set (20kg)', 'Cult', 8499, 5999, 10, True),
        ('Decathlon Yoga Mat (6mm)', 'Decathlon', 1499, 999, 30, False),
        ('Boldfit Adjustable Dumbbells (10kg Pair)', 'Boldfit', 4999, 3499, 18, True),
        ('Pro Boxing Gloves (Venum)', 'Venum', 3999, 2799, 12, False),
        ('Skechers Go Walk 6 (Walking Shoes)', 'Skechers', 6999, 4999, 22, True),
        ('Wilson Tennis Racket (Blade 98)', 'Wilson', 15999, 11999, 8, False),
        ('Cosco Cricket Bat (English Willow)', 'Cosco', 5999, 3999, 14, True),
        ('Fire-Bolt Smart Band (Black)', 'Fire-Bolt', 3999, 1999, 25, False),
    ],
    'Books & Stationery': [
        ('Atomic Habits by James Clear', 'Penguin', 599, 399, 50, True),
        ('The Alchemist by Paulo Coelho', 'HarperCollins', 499, 299, 45, False),
        ('Rich Dad Poor Dad by Robert Kiyosaki', 'Plata', 399, 249, 60, True),
        ('Ikigai by Hector Garcia', 'Penguin', 399, 249, 55, False),
        ('Think and Grow Rich by Napoleon Hill', 'HPI', 299, 199, 40, True),
        ('Classmate Notebook (A4, 172 Pages)', 'Classmate', 299, 149, 100, False),
        ('Parker Vector Pen (Matte Black)', 'Parker', 799, 549, 35, True),
        ('Cello Whiteboard Marker (Pack of 10)', 'Cello', 299, 179, 80, False),
        ('Faber-Castell Pencil Set (Pack of 10)', 'Faber-Castell', 199, 129, 90, True),
        ('Oxford School Bag (Blue, 35L)', 'Oxford', 2499, 1499, 20, False),
    ],
    'Beauty & Personal Care': [
        ('Lakme Absolute Matte Lipstick (Red)', 'Lakme', 999, 699, 30, True),
        ('Maybelline Fit Me Foundation (Natural)', 'Maybelline', 799, 549, 25, False),
        ('Nivea Body Lotion (400ml)', 'Nivea', 499, 349, 40, True),
        ('Loreal Paris Shampoo (200ml)', 'Loreal', 599, 399, 35, False),
        ('Nykaa Eyeshadow Palette (Warm Brown)', 'Nykaa', 1499, 999, 20, True),
        ('Gillette Fusion5 Razor (4 Cartridges)', 'Gillette', 899, 649, 28, False),
        ('Bombay Shaving Company Face Wash', 'BSC', 399, 249, 45, True),
        ('The Body Shop Tea Tree Oil (20ml)', 'The Body Shop', 1499, 999, 18, False),
        ('Mamaearth Vitamin C Serum (25ml)', 'Mamaearth', 699, 499, 32, True),
        ('Plum Green Tea Face Wash (100ml)', 'Plum', 499, 349, 38, False),
    ],
    'Footwear': [
        ('Puma Palermo Sneakers (White/Black)', 'Puma', 6999, 3999, 20, True),
        ('Nike Air Max SC (White)', 'Nike', 6995, 4995, 18, False),
        ('Adidas Gazelle (Blue)', 'Adidas', 8999, 5999, 15, True),
        ('Woodland Leather Boots (Brown)', 'Woodland', 4999, 2999, 22, False),
        ('Bata Floatz Flip Flops (Black)', 'Bata', 899, 499, 30, True),
        ('Reebok Running Shoes (Grey)', 'Reebok', 5499, 3499, 25, False),
        ('Crocs Classic Clogs (Navy)', 'Crocs', 2999, 1999, 18, True),
        ('Campus Sports Shoes (Black)', 'Campus', 1799, 999, 28, False),
        ('Clarks Men Loafers (Tan)', 'Clarks', 5999, 3999, 12, True),
        ('Liberty Sandals (Black)', 'Liberty', 1299, 699, 35, False),
    ],
    'Watches': [
        ('Titan Karishma Analog Watch', 'Titan', 3495, 2195, 15, True),
        ('Fastrack Reflex 3.0 (Black)', 'Fastrack', 2995, 1995, 20, False),
        ('Casio G-Shock GA-2100', 'Casio', 12995, 9995, 10, True),
        ('Fossil Grant Chronograph Watch', 'Fossil', 18995, 13995, 12, False),
        ('Seiko 5 Sports (Automatic)', 'Seiko', 19995, 15995, 8, True),
        ('Timex Expedition (Blue Dial)', 'Timex', 3995, 2495, 18, False),
        ('Sonata Quartz Watch (Silver)', 'Sonata', 1295, 695, 30, True),
        ('HMT Automatic Watch', 'HMT', 4495, 3495, 6, False),
        ('Diesel Renegade Watch (Black)', 'Diesel', 22995, 17995, 5, True),
        ('Daniel Wellington Classic Watch', 'Daniel Wellington', 10995, 7995, 14, False),
    ],
    'Bags & Luggage': [
        ('American Tourister Suitcase (68cm)', 'American Tourister', 9499, 6499, 15, True),
        ('Skybags Backpack (40L)', 'Skybags', 2499, 1499, 20, False),
        ('Wildcraft Duffle Bag (Black)', 'Wildcraft', 2999, 1999, 18, True),
        ('VIP Trolley Bag (Red)', 'VIP', 5999, 3999, 12, False),
        ('Dell Laptop Bag (15.6 inch)', 'Dell', 1799, 999, 25, True),
        ('Tommy Hilfiger Leather Wallet', 'Tommy Hilfiger', 3499, 2499, 10, False),
        ('Fastrack Laptop Backpack (Grey)', 'Fastrack', 1599, 899, 30, True),
        ('Safari Business Laptop Bag', 'Safari', 2299, 1299, 22, False),
        ('Lavie Womens Handbag (Beige)', 'Lavie', 1899, 999, 28, True),
        ('Caprese Handbag (Black)', 'Caprese', 2499, 1499, 16, False),
    ],
    'Jewellery': [
        ('Tanishq Gold-Plated Necklace Set', 'Tanishq', 4999, 3499, 10, True),
        ('Malabar 925 Silver Earrings', 'Malabar', 2999, 1999, 15, False),
        ('Voylla Kundan Necklace (Pink)', 'Voylla', 1999, 1299, 20, True),
        ('Pipa Bella Rose Gold Ring', 'Pipa Bella', 1499, 899, 25, False),
        ('Kalyan Diamond Stud Earrings', 'Kalyan', 9999, 7499, 8, True),
        ('Zaveri Pearl Mala (White)', 'Zaveri', 2999, 1999, 12, False),
        ('Forever Precious Gold Chain', 'Forever Precious', 5999, 4499, 6, True),
        ('CaratLane Solitaire Ring', 'CaratLane', 7999, 5999, 9, False),
        ('Meera Jewels Bangles Set (Red)', 'Meera Jewels', 2499, 1699, 18, True),
        ('Siaani Chandelier Earrings (Gold)', 'Siaani', 1699, 999, 22, False),
    ],
    'Toys & Baby': [
        ('LEGO City Police Station', 'LEGO', 5999, 4799, 10, True),
        ('Hot Wheels 20-Car Gift Pack', 'Hot Wheels', 2299, 1599, 15, False),
        ('Barbie DreamHouse', 'Barbie', 12999, 9999, 8, True),
        ('Fisher-Price Baby Bouncer', 'Fisher-Price', 4999, 3499, 12, False),
        ('Funskool Scrabble Board Game', 'Funskool', 1299, 899, 20, True),
        ('Mattel Uno Card Game', 'Mattel', 199, 149, 40, False),
        ('Munchkin Baby Feeding Set', 'Munchkin', 1499, 999, 25, True),
        ('Nuby Sipper (Blue)', 'Nuby', 699, 449, 30, False),
        ('Hamleys Teddy Bear (Large)', 'Hamleys', 2499, 1699, 14, True),
        ('Crayola Art Set (64 Pieces)', 'Crayola', 1599, 999, 18, False),
    ],
    'Grocery & Snacks': [
        ('Tata Salt (1kg)', 'Tata', 30, 25, 500, False),
        ('Aashirvaad Atta (5kg)', 'Aashirvaad', 260, 219, 300, True),
        ('Fortune Sunflower Oil (1L)', 'Fortune', 160, 135, 250, False),
        ('Britannia Good Day Biscuits (400g)', 'Britannia', 100, 85, 400, True),
        ('Parle-G Biscuits (1kg)', 'Parle', 120, 100, 350, False),
        ('Haldirams Namkeen Combo (1kg)', 'Haldiram', 350, 279, 200, True),
        ('Amul Butter (500g)', 'Amul', 275, 240, 180, False),
        ('Red Label Tea (500g)', 'Red Label', 250, 210, 220, True),
        ('Bournvita (1kg)', 'Bournvita', 460, 399, 150, False),
        ('Maggi Noodles (12 Pack)', 'Nestle', 240, 199, 260, True),
    ],
}


class Command(BaseCommand):
    help = 'Seed all products and categories'

    def handle(self, *args, **options):
        for cat_name, items in cat_products.items():
            cat, created = Catagory.objects.get_or_create(
                name=cat_name,
                defaults={
                    'description': f'Best {cat_name.lower()} collection',
                    'status': False,
                }
            )
            if created:
                self.stdout.write(f'Created category: {cat_name}')

            for name, vendor, orig, sell, qty, trending in items:
                obj, created = Product.objects.get_or_create(
                    name=name,
                    defaults={
                        'category': cat,
                        'vendor': vendor,
                        'original_price': orig,
                        'selling_price': sell,
                        'quantity': qty,
                        'description': f'{name} by {vendor}',
                        'status': False,
                        'trending': trending,
                    }
                )
                if created:
                    self.stdout.write(f'  Added: [{cat_name}] {name}')
                else:
                    self.stdout.write(f'  Skipped (exists): {name}')

        self.stdout.write(self.style.SUCCESS('Done!'))
