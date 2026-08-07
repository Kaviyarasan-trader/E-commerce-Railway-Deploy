import io
from django.core.management.base import BaseCommand
from django.core.files.base import ContentFile
from PIL import Image, ImageDraw, ImageFont
from shop.models import Catagory, Product
from shop.management.commands.add_category_images import cat_colors

NEW_CATEGORIES = {
    'Furniture': 'Furniture for every home',
    'Automotive Accessories': 'Car and bike accessories',
    'Pet Supplies': 'Everything your pet needs',
    'Health & Wellness': 'Stay healthy, stay strong',
    'Office Supplies': 'All your office essentials',
    'Garden & Outdoor': 'Grow your own green space',
    'Musical Instruments': 'Music gear for every player',
    'Cameras & Photography': 'Capture every moment',
    'Video Games & Consoles': 'Play the latest titles',
    'Travel & Adventure': 'Gear for the road ahead',
}

VARIANTS = {
    'Mobiles': ['Black, 128 GB', 'Black, 256 GB', 'White, 256 GB', 'White, 512 GB', 'Blue, 256 GB', 'Titanium, 512 GB', 'Red, 128 GB', 'Grey, 256 GB', 'Purple, 512 GB', 'Green, 256 GB'],
    'Shirts For Men': ['S, White', 'M, White', 'L, White', 'XL, White', 'S, Blue', 'M, Blue', 'L, Blue', 'XL, Black', 'L, Black', 'M, Grey'],
    'Pants For Men': ['28, Blue', '30, Blue', '32, Blue', '34, Blue', '30, Black', '32, Black', '34, Black', '32, Grey', '30, Khaki', '32, Navy'],
    'Cloths For Ladies': ['S', 'M', 'L', 'XL', 'XXL', 'M, Blue', 'M, Pink', 'L, Red', 'S, Black', 'M, Green'],
    'Electronics': ['Black, 256 GB', 'Black, 512 GB', 'Silver, 512 GB', 'Grey, 1 TB', 'Space Black, 512 GB', 'White, 256 GB', 'Blue, 512 GB', 'Gold, 256 GB', 'Black, 128 GB', 'Slate, 512 GB'],
    'Home & Kitchen': ['Steel', 'Black', 'White', 'Silver', 'Red', 'Blue', 'Copper', 'Gold', 'Grey', 'Teal'],
    'Sports & Fitness': ['Black', 'Blue', 'Red', 'Grey', 'White', 'Green', 'Navy', 'Orange', 'Pink', 'Yellow'],
    'Books & Stationery': ['Paperback', 'Hardcover', 'Kindle Edition', 'Audiobook', 'Special Edition', 'Classic Edition', 'Mass Market', 'Deluxe Edition', 'Box Set', 'Pocket Edition'],
    'Beauty & Personal Care': ['100ml', '200ml', '250ml', '400ml', '500ml', '50ml', '150ml', '300ml', '75ml', '600ml'],
    'Footwear': ['UK 6', 'UK 7', 'UK 8', 'UK 9', 'UK 10', 'UK 11', 'UK 12', 'UK 5', 'UK 6.5', 'UK 8.5'],
    'Watches': ['Black Dial', 'Blue Dial', 'Silver Dial', 'Gold Dial', 'White Dial', 'Green Dial', 'Rose Gold', 'Brown Dial', 'Grey Dial', 'Red Dial'],
    'Bags & Luggage': ['Black', 'Brown', 'Blue', 'Grey', 'Red', 'Navy', 'Green', 'Tan', 'Charcoal', 'Olive'],
    'Jewellery': ['Gold', 'Silver', 'Rose Gold', 'White Gold', 'Oxidised', 'Kundan', 'Pearl', 'Platinum', 'Brass', 'Sterling'],
    'Toys & Baby': ['Small', 'Medium', 'Large', 'XL', 'Classic', 'Deluxe', 'Junior', 'Premium', 'Giant', 'Mini'],
    'Grocery & Snacks': ['1kg', '500g', '250g', '2kg', '5kg', '1L', '2L', '10kg', '750g', '3kg'],
    'Furniture': ['Walnut', 'Oak', 'Black', 'White', 'Teak', 'Grey', 'Brown', 'Natural', 'Cream', 'Ash'],
    'Automotive Accessories': ['Black', 'Silver', 'Chrome', 'Red', 'Blue', 'Grey', 'White', 'Carbon', 'Green', 'Matte Black'],
    'Pet Supplies': ['Small', 'Medium', 'Large', 'X-Large', '2kg', '5kg', '10kg', '15kg', '1L', '500g'],
    'Health & Wellness': ['100ml', '200ml', '250ml', '500ml', '1kg', '500g', 'Pack of 10', 'Pack of 20', 'Pack of 30', '60 Tablets'],
    'Office Supplies': ['Pack of 5', 'Pack of 10', 'Pack of 20', 'Pack of 50', 'Pack of 100', 'Black', 'Blue', 'Red', 'Green', 'Mixed'],
    'Garden & Outdoor': ['Small', 'Medium', 'Large', 'XL', 'Green', 'Brown', 'Black', 'White', 'Terracotta', 'Ceramic'],
    'Musical Instruments': ['Beginner', 'Standard', 'Pro', 'Black', 'Natural', 'Red', 'Blue', 'Sunburst', 'Matte', 'Glossy'],
    'Cameras & Photography': ['Black', 'Silver', 'White', 'Grey', 'Body Only', 'With Kit Lens', '18-55mm', '24-70mm', 'Compact', 'Pro Bundle'],
    'Video Games & Consoles': ['Standard Edition', 'Deluxe Edition', 'Collectors Edition', 'Digital Code', 'Physical Disc', 'With 1 Controller', 'With 2 Controllers', 'Bundle', 'New', 'Pre-Owned'],
    'Travel & Adventure': ['Small', 'Medium', 'Large', 'XL', 'Black', 'Grey', 'Blue', 'Red', 'Green', 'Olive'],
}

BASES = {
    'Mobiles': [
        ('Samsung Galaxy A56 5G', 'Samsung', 39999, 32999),
        ('OnePlus Nord 5 5G', 'OnePlus', 29999, 24999),
        ('Xiaomi Redmi Note 14 Pro', 'Xiaomi', 24999, 19999),
        ('Realme Narzo 70 Pro', 'Realme', 19999, 15999),
        ('Vivo V50 5G', 'Vivo', 34999, 29999),
        ('iQOO Neo 10 Pro', 'iQOO', 39999, 32999),
        ('Nothing CMF Phone 2', 'Nothing', 22999, 17999),
        ('Motorola Edge 50 Neo', 'Motorola', 32999, 27999),
        ('Poco X7 Pro', 'Poco', 27999, 22999),
        ('Infinix Note 50 Pro', 'Infinix', 17999, 13999),
    ],
    'Shirts For Men': [
        ('Allen Solly Casual Shirt', 'Allen Solly', 1799, 999),
        ('John Players Casual Shirt', 'John Players', 1499, 799),
        ('Raymond Formal Shirt', 'Raymond', 2499, 1499),
        ('Park Avenue Formal Shirt', 'Park Avenue', 2199, 1299),
        ('Zodiac Slim Fit Shirt', 'Zodiac', 2699, 1699),
        ('Blackberrys Regular Shirt', 'Blackberrys', 2999, 1799),
        ('Monte Carlo Casual Shirt', 'Monte Carlo', 1899, 1099),
        ('Safari Formal Shirt', 'Safari', 1999, 1199),
        ('Andiamo Check Shirt', 'Andiamo', 1599, 899),
        ('Ecko Unltd Printed Shirt', 'Ecko Unltd', 1699, 949),
    ],
    'Pants For Men': [
        ('Wrangler Regular Jeans', 'Wrangler', 2999, 1899),
        ('Flying Machine Jeans', 'Flying Machine', 2699, 1599),
        ('Pepe Jeans Slim Fit', 'Pepe Jeans', 3299, 2099),
        ('Killer Jeans', 'Killer', 2799, 1699),
        ('Being Human Jeans', 'Being Human', 2899, 1799),
        ('Levi 501 Original Jeans', 'Levi', 4499, 3199),
        ('U.S. Polo Chinos', 'U.S. Polo', 2599, 1499),
        ('Tommy Hilfiger Jeans', 'Tommy Hilfiger', 5499, 3999),
        ('Calvin Klein Jeans', 'Calvin Klein', 5999, 4299),
        ('Nautica Chinos', 'Nautica', 3499, 2299),
    ],
    'Cloths For Ladies': [
        ('Fabindia Cotton Kurti', 'Fabindia', 1999, 1199),
        ('Biba Anarkali Kurta', 'Biba', 2499, 1499),
        ('W Ethnic Tunic', 'W', 1799, 999),
        ('H&M Casual Top', 'H&M', 1299, 749),
        ('Zara Summer Dress', 'Zara', 3999, 2499),
        ('Forever 21 Denim Dress', 'Forever 21', 2499, 1499),
        ('Mango Midi Dress', 'Mango', 2999, 1899),
        ('Vero Moda Jeans', 'Vero Moda', 2799, 1699),
        ('Only Denim Jacket', 'Only', 3499, 2199),
        ('SASSAFras Crop Top', 'SASSAFras', 999, 549),
    ],
    'Electronics': [
        ('HP Pavilion Laptop', 'HP', 65990, 58990),
        ('Lenovo IdeaPad Slim 5', 'Lenovo', 70990, 62990),
        ('Asus Vivobook 15', 'Asus', 57990, 49990),
        ('Acer Aspire 5', 'Acer', 54990, 46990),
        ('Dell Inspiron 15', 'Dell', 67990, 59990),
        ('Samsung Galaxy Book4', 'Samsung', 89990, 79990),
        ('Microsoft Surface Laptop 7', 'Microsoft', 119990, 104990),
        ('Asus TUF Gaming F15', 'Asus', 99990, 87990),
        ('MSI Katana 15 Gaming', 'MSI', 114990, 99990),
        ('LG Gram 16', 'LG', 124990, 109990),
    ],
    'Home & Kitchen': [
        ('Prestige Cookware Set', 'Prestige', 4999, 3499),
        ('Cello Insulated Bottle', 'Cello', 1499, 899),
        ('Borosil Glass Jars Set', 'Borosil', 1999, 1299),
        ('Havells Room Heater', 'Havells', 3999, 2799),
        ('Usha Ceiling Fan', 'Usha', 2999, 1999),
        ('Crompton Air Cooler', 'Crompton', 8999, 6499),
        ('Elica Kitchen Chimney', 'Elica', 14999, 11999),
        ('Whirlpool Washing Machine', 'Whirlpool', 27999, 23999),
        ('Samsung Double Door Fridge', 'Samsung', 32999, 27999),
        ('IFB Dishwasher', 'IFB', 39999, 34999),
    ],
    'Sports & Fitness': [
        ('Nike Dri-FIT T-Shirt', 'Nike', 2495, 1495),
        ('Adidas Training Track Pants', 'Adidas', 3495, 1995),
        ('Puma Training Kit', 'Puma', 3995, 2395),
        ('Reebok Gym Duffel Bag', 'Reebok', 1999, 1199),
        ('Sparx Running Shoes', 'Sparx', 1999, 1199),
        ('Asics Gel Running Shoes', 'Asics', 6999, 4999),
        ('New Balance Sneakers', 'New Balance', 8499, 5999),
        ('Under Armour Sports Top', 'Under Armour', 2999, 1799),
        ('Wilson Football', 'Wilson', 1999, 1299),
        ('Nivia Basketball', 'Nivia', 1499, 899),
    ],
    'Books & Stationery': [
        ('The Psychology of Money', 'Morgan Housel', 699, 449),
        ('Deep Work by Cal Newport', 'Cal Newport', 799, 499),
        ('Sapiens by Yuval Noah Harari', 'Yuval Noah Harari', 999, 649),
        ('Zero to One by Peter Thiel', 'Peter Thiel', 599, 399),
        ('The Lean Startup', 'Eric Ries', 899, 599),
        ('Dopamine Nation', 'Anna Lembke', 699, 449),
        ('Meditations by Marcus Aurelius', 'Marcus Aurelius', 499, 299),
        ('The Richest Man in Babylon', 'George S. Clason', 399, 249),
        ('Start With Why', 'Simon Sinek', 599, 399),
        ('The 5 AM Club', 'Robin Sharma', 799, 499),
    ],
    'Beauty & Personal Care': [
        ('Loreal Paris Face Serum', 'Loreal', 1499, 999),
        ('CeraVe Moisturizing Cream', 'CeraVe', 1799, 1299),
        ('Neutrogena Sunscreen SPF50', 'Neutrogena', 799, 549),
        ('Dove Deep Moisture Body Wash', 'Dove', 499, 349),
        ('Cetaphil Gentle Cleanser', 'Cetaphil', 999, 699),
        ('Garnier Brightening Face Pack', 'Garnier', 399, 249),
        ('Tresemme Keratin Conditioner', 'Tresemme', 699, 449),
        ('Old Spice Deodorant', 'Old Spice', 349, 229),
        ('Biotique Clarifying Face Cream', 'Biotique', 399, 279),
        ('Minimalist 10% Vitamin C Serum', 'Minimalist', 699, 499),
    ],
    'Footwear': [
        ('Puma Court Sneakers', 'Puma', 5499, 3499),
        ('Adidas Samba Classic', 'Adidas', 9999, 6999),
        ('Nike Court Legacy', 'Nike', 5495, 3995),
        ('Skechers D Lite', 'Skechers', 6999, 4999),
        ('Sparx Sports Sandals', 'Sparx', 1499, 899),
        ('Paragon Comfort Slippers', 'Paragon', 799, 449),
        ('Red Chief Formal Shoes', 'Red Chief', 3499, 2199),
        ('Hush Puppies Casual Shoes', 'Hush Puppies', 4999, 3499),
        ('Metro Leather Loafers', 'Metro Shoes', 2999, 1899),
        ('Fila Retro Sneakers', 'Fila', 4999, 3299),
    ],
    'Watches': [
        ('Titan Neo Analog Watch', 'Titan', 1995, 1295),
        ('Fastrack Reflex Play', 'Fastrack', 4495, 2995),
        ('Casio Vintage Collection', 'Casio', 2995, 1995),
        ('Sonata Poze Quartz', 'Sonata', 1495, 895),
        ('Timex Weekender', 'Timex', 3995, 2495),
        ('Fossil Minimalist Watch', 'Fossil', 12995, 9995),
        ('Emporio Armani Chronograph', 'Armani', 34995, 27995),
        ('Noise ColorFit Pro 5', 'Noise', 4999, 3499),
        ('Fire-Bolt Ninja Smartwatch', 'Fire-Bolt', 2999, 1999),
        ('G-Shock GA-700', 'Casio', 9995, 7995),
    ],
    'Bags & Luggage': [
        ('Skybags 24 inch Trolley', 'Skybags', 3999, 2499),
        ('American Tourister Cabin', 'American Tourister', 7999, 5499),
        ('Safari 68cm Suitcase', 'Safari', 5499, 3799),
        ('Wildcraft 32L Backpack', 'Wildcraft', 2499, 1499),
        ('Delsey Hard Luggage', 'Delsey', 12999, 9499),
        ('Lenovo Laptop Sleeve', 'Lenovo', 999, 599),
        ('HP Business Backpack', 'HP', 1999, 1199),
        ('Samsonite Cabin Bag', 'Samsonite', 11999, 8999),
        ('Aristocrat 4 Wheeler', 'Aristocrat', 4499, 2799),
        ('Nike Gym Duffle', 'Nike', 2999, 1899),
    ],
    'Jewellery': [
        ('Tanishq Gold Ring', 'Tanishq', 5999, 4499),
        ('Kalyan Kundan Necklace', 'Kalyan', 4999, 3499),
        ('CaratLane Diamond Pendant', 'CaratLane', 12999, 9999),
        ('GIVA Silver Ring', 'GIVA', 1999, 1299),
        ('Voylla Chandbali Earrings', 'Voylla', 2499, 1499),
        ('Zaveri Nose Pin', 'Zaveri', 1499, 899),
        ('Pipa Bella Bracelet', 'Pipa Bella', 1799, 1099),
        ('Siaani Bridal Necklace', 'Siaani', 3999, 2499),
        ('Meera Gold Bangles', 'Meera Jewels', 2999, 1999),
        ('Forever Precious Pearl Mala', 'Forever Precious', 3499, 2299),
    ],
    'Toys & Baby': [
        ('LEGO Creator 3-in-1 Set', 'LEGO', 3999, 3299),
        ('Hot Wheels Track Set', 'Hot Wheels', 1499, 999),
        ('Barbie Fashion Doll', 'Barbie', 2499, 1699),
        ('Nerf Elite Blaster', 'Nerf', 2999, 1999),
        ('Fisher-Price Musical Toy', 'Fisher-Price', 1999, 1299),
        ('Mickey Plush Toy', 'Disney', 1499, 999),
        ('Pictionary Board Game', 'Hasbro', 1999, 1299),
        ('Jenga Classic Game', 'Hasbro', 1499, 949),
        ('Rubik Cube Speed', 'Rubik', 999, 599),
        ('Classic Teddy Bear', 'Hamleys', 1999, 1299),
    ],
    'Grocery & Snacks': [
        ('Saffola Gold Oil', 'Saffola', 799, 699),
        ('Fortune Basmati Rice', 'Fortune', 999, 849),
        ('Tata Tea Gold', 'Tata', 299, 249),
        ('Nestle Corn Flakes', 'Nestle', 149, 119),
        ('Kelloggs Muesli', 'Kelloggs', 499, 399),
        ('Haldiram Papad Pack', 'Haldiram', 199, 149),
        ('Bikaji Bhujia', 'Bikaji', 249, 189),
        ('Mother Dairy Paneer', 'Mother Dairy', 179, 149),
        ('Amul Cheese Block', 'Amul', 299, 249),
        ('Cadbury Dairy Milk', 'Cadbury', 150, 119),
    ],
    'Furniture': [
        ('Wakefit Ortho Mattress', 'Wakefit', 18999, 12999),
        ('Durian Queen Bed Frame', 'Durian', 27999, 19999),
        ('Nilkamal Ergonomic Chair', 'Nilkamal', 4999, 3499),
        ('Godrej 3 Seater Sofa', 'Godrej', 34999, 27999),
        ('Home Centre Wardrobe', 'Home Centre', 25999, 19999),
        ('Urban Ladder Coffee Table', 'Urban Ladder', 8999, 6499),
        ('Wooden Street Study Desk', 'Wooden Street', 14999, 10999),
        ('Pepperfry Bookshelf', 'Pepperfry', 11999, 8999),
        ('Bajaj Recliner Chair', 'Bajaj', 18999, 13999),
        ('Interwood TV Unit', 'Interwood', 21999, 16999),
    ],
    'Automotive Accessories': [
        ('Michelin Car Tyre', 'Michelin', 8999, 7499),
        ('Bridgestone Bike Tyre', 'Bridgestone', 2999, 2399),
        ('Bosch Car Battery', 'Bosch', 6999, 5999),
        ('Philips Headlight Bulb', 'Philips', 999, 699),
        ('Hero Motorsafe Helmet', 'Hero', 1999, 1499),
        ('Vega Full Face Helmet', 'Vega', 2499, 1799),
        ('GoPro Car Mount', 'GoPro', 2999, 2199),
        ('WD-40 Multi-Use Spray', 'WD-40', 499, 349),
        ('Castrol Engine Oil', 'Castrol', 999, 799),
        ('3M Car Care Polish', '3M', 1499, 1099),
    ],
    'Pet Supplies': [
        ('Pedigree Adult Dog Food', 'Pedigree', 999, 799),
        ('Whiskas Cat Food', 'Whiskas', 899, 699),
        ('Pet India Dog Bowl', 'Pet India', 399, 249),
        ('Royal Canin Puppy Food', 'Royal Canin', 1999, 1599),
        ('Ohh My Dog Shampoo', 'Ohh My Dog', 499, 349),
        ('Prey Cat Litter', 'Prey', 699, 499),
        ('Petzo Dog Bed', 'Petzo', 1499, 999),
        ('Himalayan Pet Dental Chew', 'Himalayan', 499, 349),
        ('Pupperrier Leash', 'Pupperrier', 599, 399),
        ('Doggy World Harness', 'Doggy World', 799, 549),
    ],
    'Health & Wellness': [
        ('Dr Morepen BP Monitor', 'Dr Morepen', 2999, 1999),
        ('Omron Digital Thermometer', 'Omron', 999, 699),
        ('Accu-Chek Glucometer', 'Accu-Chek', 1999, 1499),
        ('Digene Acidity Tablets', 'Digene', 199, 149),
        ('Dabur Chyawanprash', 'Dabur', 499, 399),
        ('Himalaya Ashwagandha', 'Himalaya', 399, 299),
        ('Baidyanath Shilajit', 'Baidyanath', 1499, 1099),
        ('Ensure Nutrition Shake', 'Ensure', 999, 799),
        ('Whey Protein Concentrate', 'MuscleBlaze', 2999, 2199),
        ('Fish Oil Omega-3 Capsules', 'Seven Seas', 799, 599),
    ],
    'Office Supplies': [
        ('Apsara ABS Pencils', 'Apsara', 299, 199),
        ('Camlin Sketch Pens', 'Camlin', 399, 249),
        ('Maped Geometry Box', 'Maped', 349, 219),
        ('Kangaro Heavy Stapler', 'Kangaro', 499, 329),
        ('Kores Paper Clips', 'Kores', 149, 99),
        ('Avery Label Stickers', 'Avery', 299, 199),
        ('Safari Pen Holder', 'Safari', 249, 149),
        ('Deli Titanium Scissors', 'Deli', 399, 249),
        ('OXYPURE A4 Sheets', 'OXYPURE', 349, 249),
        ('Faber-Castell Highlighter', 'Faber-Castell', 299, 189),
    ],
    'Garden & Outdoor': [
        ('NurseryLive Rose Plant', 'NurseryLive', 299, 199),
        ('Ugaoo Seed Starter Kit', 'Ugaoo', 499, 349),
        ('Kisan Garden Tool Set', 'Kisan', 1299, 899),
        ('Wilson Garden Hose', 'Wilson', 1499, 999),
        ('Birla Garden Sprayer', 'Birla', 899, 599),
        ('Green Decor Plant Pot', 'Green Decor', 599, 399),
        ('Vertise Soil Mix 5kg', 'Vertise', 399, 279),
        ('Jain Bonsai Tree', 'Jain', 2499, 1799),
        ('Yewale Organic Fertilizer', 'Yewale', 499, 349),
        ('Bloom Garden Gloves', 'Bloom', 299, 199),
    ],
    'Musical Instruments': [
        ('Bajaao Guitar Starter Pack', 'Bajaao', 9999, 6999),
        ('Yamaha F310 Acoustic Guitar', 'Yamaha', 11999, 8999),
        ('Vault Piano Keyboard', 'Vault', 14999, 10999),
        ('Casio CT-S1 Keyboard', 'Casio', 19999, 15999),
        ('Synsonic Electronic Drum', 'Synsonic', 29999, 21999),
        ('Mapex Snare Drum', 'Mapex', 19999, 14999),
        ('Behringer Studio Headphones', 'Behringer', 4999, 3499),
        ('Stagg Violin 4/4', 'Stagg', 12999, 9499),
        ('Hohner Chromatic Harmonica', 'Hohner', 4999, 3499),
        ('Rico Saxophone Reeds', 'Rico', 1499, 999),
    ],
    'Cameras & Photography': [
        ('Sony Alpha A6100', 'Sony', 69990, 59990),
        ('Canon EOS R50', 'Canon', 74990, 64990),
        ('Nikon Z50', 'Nikon', 84990, 74990),
        ('GoPro Hero 13', 'GoPro', 39990, 34990),
        ('DJI Mini 4K Drone', 'DJI', 29990, 24990),
        ('Instax Mini 12 Camera', 'Fujifilm', 4999, 3999),
        ('Panasonic Lumix G7', 'Panasonic', 54990, 47990),
        ('Fujifilm X100VI', 'Fujifilm', 159990, 139990),
        ('Tamron 28-75mm Lens', 'Tamron', 79990, 69990),
        ('Manfrotto Tripod', 'Manfrotto', 14990, 10990),
    ],
    'Video Games & Consoles': [
        ('Sony PS5 Slim Console', 'Sony', 54990, 49990),
        ('Xbox Series X', 'Microsoft', 54990, 49990),
        ('Nintendo Switch 2', 'Nintendo', 39990, 35990),
        ('GTA VI Premium', 'Rockstar', 4999, 3999),
        ('EA FC 26', 'EA Sports', 3999, 3299),
        ('Mortal Kombat 1', 'Warner Bros', 3999, 2999),
        ('God of War Ragnarok', 'PlayStation', 4499, 3499),
        ('Marvel Spiderman 2', 'PlayStation', 4999, 3999),
        ('Legend of Zelda', 'Nintendo', 4499, 3599),
        ('Minecraft Deluxe', 'Mojang', 1999, 1499),
    ],
    'Travel & Adventure': [
        ('Skybags Cabin Trolley', 'Skybags', 4999, 3499),
        ('Samsonite Carry-On', 'Samsonite', 13999, 9999),
        ('Wildcraft 45L Rucksack', 'Wildcraft', 3999, 2799),
        ('Victorinox Duffle', 'Victorinox', 19999, 14999),
        ('Osprey Hiking Pack', 'Osprey', 15999, 11999),
        ('Decathlon 2P Tent', 'Decathlon', 5999, 4499),
        ('Quechua Sleeping Bag', 'Quechua', 2499, 1799),
        ('Coleman Camp Stove', 'Coleman', 3999, 2999),
        ('Safari Travel Kit', 'Safari', 1499, 999),
        ('Terra Tracker GPS', 'Terra', 9999, 7499),
    ],
}


def make_gradient(w, h, top, bottom):
    grad = Image.new('RGB', (1, h))
    for y in range(h):
        t = y / max(h - 1, 1)
        grad.putpixel((0, y), (
            int(top[0] + (bottom[0] - top[0]) * t),
            int(top[1] + (bottom[1] - top[1]) * t),
            int(top[2] + (bottom[2] - top[2]) * t),
        ))
    img = grad.resize((w, h))
    return img


def make_product_placeholder(product):
    top, bottom = cat_colors.get(product.category.name, ((60, 52, 137), (107, 91, 214)))
    img = make_gradient(400, 400, top, bottom)
    draw = ImageDraw.Draw(img, 'RGBA')
    draw.ellipse((-80, -80, 220, 220), fill=(255, 255, 255, 22))
    draw.ellipse((280, 280, 480, 480), fill=(255, 255, 255, 18))
    try:
        font = ImageFont.truetype("arialbd.ttf", 24)
        font_s = ImageFont.truetype("arial.ttf", 16)
    except Exception:
        try:
            font = ImageFont.truetype("arial.ttf", 24)
            font_s = ImageFont.truetype("arial.ttf", 16)
        except Exception:
            font = ImageFont.load_default()
            font_s = font
    short = product.name if len(product.name) <= 26 else product.name[:23] + '...'
    bbox = draw.textbbox((0, 0), short, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((400 - tw) / 2, (400 - th) / 2 - 18), short, fill=(255, 255, 255), font=font)
    price = f'Rs.{int(product.selling_price)}'
    bbox2 = draw.textbbox((0, 0), price, font=font_s)
    tw2, th2 = bbox2[2] - bbox2[0], bbox2[3] - bbox2[1]
    draw.text(((400 - tw2) / 2, (400 - th2) / 2 + 24), price, fill=(250, 199, 117), font=font_s)
    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=82)
    buf.seek(0)
    return ContentFile(buf.read())


class Command(BaseCommand):
    help = 'Create 10 new categories and grow every category to 100 products'

    def handle(self, *args, **options):
        for name, desc in NEW_CATEGORIES.items():
            cat, created = Catagory.objects.get_or_create(
                name=name,
                defaults={'description': desc, 'status': False},
            )
            if created:
                self.stdout.write(f'Created category: {name}')

        created_total = 0
        for cat_name, bases in BASES.items():
            cat = Catagory.objects.get(name=cat_name)
            existing = Product.objects.filter(category=cat).count()
            needed = max(0, 100 - existing)
            if needed == 0:
                self.stdout.write(f'[skip] {cat_name} already has {existing} products')
                continue

            variants = VARIANTS[cat_name]
            seen = set(Product.objects.filter(category=cat).values_list('name', flat=True))
            made = 0
            vi = 0
            while made < needed:
                base = bases[made % len(bases)]
                variant = variants[vi % len(variants)]
                name = f'{base[0]} ({variant})'
                if name in seen:
                    vi += 1
                    continue
                seen.add(name)
                _, vendor, orig, sell = base
                qty = ((made % 7) + 1) * 12 + (vi % 5) * 5
                product = Product.objects.create(
                    name=name,
                    vendor=vendor,
                    category=cat,
                    original_price=orig,
                    selling_price=sell,
                    quantity=qty,
                    description=f'{name} by {vendor}',
                    status=False,
                    trending=(vi % 5 == 0),
                )
                img = make_product_placeholder(product)
                product.product_image.save(f'product_{product.id}.jpg', img, save=True)
                made += 1
                vi += 1
                created_total += 1
            self.stdout.write(f'{cat_name}: now {existing + made} products (+{made})')

        self.stdout.write(self.style.SUCCESS(f'Done! Created {created_total} products.'))
