"""Intelligent natural-language search over the local KaviBazaar catalog.

Pure Django ORM + Python standard library (re, difflib). No external
packages, no AI APIs, no network calls. Everything runs against the local
database.

Pipeline:
    parse -> expand (synonyms / spelling / plural) -> ORM filter
    -> relevance score -> rank -> relaxed retry -> related fallback

Only filtered candidates are loaded into memory (bounded by ``rank_limit``);
a plain ORM queryset is returned for very broad queries instead of loading
the whole catalog.
"""

import re
import difflib

from django.db.models import Avg, Count, Q

from .models import Catagory, Product

SORT_MAP = {
    'price_low': 'selling_price',
    'price_high': '-selling_price',
    'name': 'name',
    'newest': '-created_at',
}

STOPWORDS = frozenset({
    'a', 'an', 'the', 'and', 'or', 'but', 'of', 'in', 'on', 'at', 'to',
    'for', 'with', 'by', 'from', 'into', 'within', 'i', 'me', 'my', 'we',
    'us', 'our', 'you', 'your', 'show', 'find', 'give', 'need', 'want',
    'looking', 'please', 'buy', 'get', 'best', 'top', 'new', 'price',
    'prices', 'product', 'products', 'online', 'shop', 'shopping', 'some',
    'any', 'all', 'one', 'two', 'can', 'could', 'would', 'under', 'below',
    'above', 'over', 'around', 'about', 'between', 'cheap', 'cheapest',
    'affordable', 'budget', 'less', 'than', 'more', 'upto', 'recommend',
    'suggest', 'items', 'item', 'only', 'offer', 'offers', 'discount',
    'delivery', 'gift', 'list', 'something', 'no', 'yes', 'please', 'also',
    'just', 'want', 'wanted', 'give', 'me', 'us', 'near', 'close',
})

GENERIC_WORDS = frozenset({
    'mobile', 'mobiles', 'phone', 'phones', 'smartphone', 'smartphones',
    'shirt', 'shirts', 'pant', 'pants', 'trouser', 'trousers',
    'dress', 'dresses', 'cloth', 'cloths', 'clothes', 'clothing',
    'shoe', 'shoes', 'footwear', 'sneaker', 'sneakers', 'sandal', 'sandals',
    'boot', 'boots', 'slipper', 'slippers', 'loafers', 'heels',
    'bag', 'bags', 'backpack', 'backpacks', 'luggage', 'handbag', 'handbags',
    'suitcase', 'trolley', 'tote', 'rucksack',
    'watch', 'watches', 'book', 'books', 'novel', 'novels', 'stationery',
    'toy', 'toys', 'camera', 'cameras', 'gadget', 'gadgets', 'electronics',
    'speaker', 'speakers', 'headphone', 'headphones', 'earbuds', 'earphones',
    'laptop', 'laptops', 'computer', 'tablet', 'tv', 'television',
    'sport', 'sports', 'fitness', 'home', 'kitchen', 'cookware', 'furniture',
    'beauty', 'cosmetic', 'cosmetics', 'skincare', 'jewellery', 'jewelry',
    'health', 'wellness', 'grocery', 'snack', 'snacks', 'travel', 'garden',
    'office', 'music', 'musical', 'instrument', 'instruments', 'game',
    'games', 'console', 'pet', 'pets', 'automotive', 'teddy', 'plush',
    'tshirt', 't-shirt', 't shirt', 'tee', 'notebook', 'notebooks',
    'perfume', 'perfumes', 'fragrance', 'pen', 'pens', 'pencil', 'pencils',
    'marker', 'copy', 'copies', 'guitar', 'guitars', 'chair', 'chairs',
    'table', 'tables', 'sofa', 'sofas', 'desk', 'desks', 'necklace', 'ring',
    'chain', 'bracelet', 'earring', 'bangle', 'shorts', 'jeans', 'jean',
    'chino', 'chinos', 'saree', 'sarees', 'salwar', 'kurti', 'kurtas',
    'lehenga', 'gown', 'gowns', 'blouse', 'skirt', 'trousers',
})

COLORS = {
    'Black': ('black',),
    'White': ('white', 'ivory', 'cream', 'offwhite'),
    'Grey': ('grey', 'gray'),
    'Blue': ('blue', 'navy', 'indigo'),
    'Red': ('red', 'maroon', 'burgundy', 'crimson'),
    'Green': ('green', 'teal', 'olive', 'emerald'),
    'Yellow': ('yellow', 'golden', 'mustard'),
    'Orange': ('orange', 'peach', 'rust'),
    'Pink': ('pink', 'rose'),
    'Purple': ('purple', 'violet', 'lavender', 'lilac'),
    'Brown': ('brown', 'tan', 'beige', 'khaki', 'chocolate'),
    'Silver': ('silver', 'steel', 'chrome'),
    'Gold': ('gold',),
    'Multicolor': ('multicolor', 'multicolour', 'colourblock'),
    'Transparent': ('transparent',),
    'Assorted': ('assorted', 'mixed'),
}

SIZE_LETTERS = {
    's': 'S', 'm': 'M', 'l': 'L', 'xl': 'XL', 'xxl': 'XXL',
    'xxxl': 'XXXL', '3xl': '3XL',
}

GENDERS = {
    'men': 'Men', 'man': 'Men', 'male': 'Men', 'gents': 'Men', 'boys': 'Men',
    'women': 'Women', 'woman': 'Women', 'female': 'Women', 'ladies': 'Women',
    'girls': 'Women',
    'kids': 'Kids', 'children': 'Kids', 'baby': 'Kids', 'infant': 'Kids',
    'toddler': 'Kids',
    'unisex': 'Unisex',
}

GENDER_CATEGORY_HINT = {
    'Men': ('Men',),
    'Women': ('Ladies', 'Women', 'Girls'),
    'Kids': ('Kids', 'Baby', 'Boys', 'Girls'),
    'Unisex': ('Unisex',),
}

SYNONYMS = {
    'tshirt': ('t shirt', 't-shirt', 'tee', 't-shirts', 'tees'),
    't-shirt': ('tshirt', 't shirt', 'tee'),
    't shirt': ('tshirt', 't-shirt', 'tee'),
    'tee': ('tshirt', 't shirt', 't-shirt', 'tees'),
    'shirt': ('shirts', 'tee'),
    'sneaker': ('sneakers', 'trainer', 'trainers', 'shoe', 'shoes'),
    'sneakers': ('sneaker', 'trainers', 'running shoe', 'running shoes'),
    'trainer': ('trainers', 'sneakers', 'running shoe'),
    'mobile': ('mobiles', 'phone', 'phones', 'smartphone', 'smartphones'),
    'phone': ('phones', 'mobile', 'mobiles', 'smartphone', 'smartphones'),
    'smartphone': ('smartphones', 'mobile', 'mobiles', 'phone', 'phones'),
    'laptop': ('laptops', 'notebook', 'notebooks'),
    'watch': ('watches', 'smartwatch', 'smartwatches'),
    'smartwatch': ('smartwatches', 'watch', 'watches'),
    'handbag': ('handbags', 'bag', 'bags'),
    'backpack': ('backpacks', 'bag', 'bags', 'rucksack'),
    'headphone': ('headphones', 'earbuds', 'earphones', 'headset'),
    'earbuds': ('earphones', 'earbud', 'true wireless', 'tws'),
    'speaker': ('speakers', 'soundbar', 'bluetooth speaker'),
    'sandal': ('sandals', 'slippers', 'flipflops'),
    'slipper': ('slippers', 'sandals', 'flipflops'),
    'shoe': ('shoes', 'sneaker', 'sneakers'),
    'shoes': ('shoe', 'sneakers', 'sneaker', 'footwear'),
    'gaming': ('game', 'games', 'console', 'controller'),
    'camera': ('cameras', 'dslr', 'mirrorless', 'lens'),
    'notebook': ('notebooks', 'books', 'copy', 'copies'),
    'stationery': ('pen', 'pens', 'pencil', 'pencils', 'notebook', 'marker'),
    'perfume': ('perfumes', 'fragrance', 'deodorant'),
    'furniture': ('chair', 'chairs', 'table', 'tables', 'sofa', 'desk'),
    'jewellery': ('jewelry', 'necklace', 'ring', 'chain', 'bracelet'),
    'jewelry': ('jewellery', 'necklace', 'ring', 'chain', 'bracelet'),
    'guitar': ('guitars', 'instrument', 'acoustic guitar'),
    'book': ('books', 'novel', 'novels', 'notebook'),
    'toy': ('toys', 'action figure', 'puzzle', 'doll'),
    'baby': ('kids', 'infant', 'toddler'),
    'kids': ('children', 'baby', 'toddler'),
    'bag': ('bags', 'backpack', 'backpacks', 'luggage', 'handbag', 'handbags'),
    'pant': ('pants', 'trousers', 'trouser', 'jeans', 'chinos', 'shorts'),
    'shirt': ('shirts', 'tee'),
    'dress': ('dresses', 'gown', 'gowns', 'kurti', 'salwar'),
    'saree': ('sarees', 'salwar', 'kurti'),
}

TYPO_FIXES = {
    'shrit': 'shirt', 'shrits': 'shirt', 'tshrit': 'tshirt',
    'tshrits': 'tshirt', 'moblie': 'mobile', 'moblies': 'mobile',
    'phonee': 'phone', 'iphoe': 'iphone', 'nikee': 'nike',
    'sneakerz': 'sneakers', 'watchs': 'watch', 'cameraa': 'camera',
    'shose': 'shoes', 't-shrit': 'tshirt', 'adidad': 'adidas',
    'samung': 'samsung', 'samsng': 'samsung', 'riebook': 'reebok',
    'adidas': 'adidas', 'wildcraft': 'wildcraft', 'skbags': 'skybags',
    'tshrit': 'tshirt', 'tshrits': 'tshirt', 't-shrit': 'tshirt',
}

_PRICE_NUM = r'\d{1,7}(?:[.,]\d{1,2})?'
_MONEY = r'(?:rs\.?\s*|inr\s*|rupees\s*)?'

CATEGORY_ALIASES = {
    'Mobiles': ('mobile', 'mobiles', 'phone', 'phones', 'smartphone',
                'smartphones', 'iphone', 'android', '5g', '4g'),
    'Electronics': ('electronics', 'gadget', 'gadgets', 'headphone',
                    'headphones', 'earbuds', 'earphones', 'speaker',
                    'speakers', 'soundbar', 'tv', 'television', 'laptop',
                    'laptops', 'computer', 'tablet', 'charger', 'mouse',
                    'keyboard', 'printer', 'router'),
    'Footwear': ('footwear', 'shoe', 'shoes', 'sneaker', 'sneakers',
                 'trainer', 'trainers', 'sandal', 'sandals', 'slippers',
                 'boot', 'boots', 'loafers', 'heels', 'sport shoes'),
    'Shirts For Men': ('shirt', 'shirts', 'tee', 'tshirt', 'polo',
                       'formal shirt', 'casual shirt'),
    'Pants For Men': ('pant', 'pants', 'trouser', 'trousers', 'jeans',
                      'jean', 'chino', 'chinos', 'shorts', 'pyjama'),
    'Cloths For Ladies': ('dress', 'dresses', 'saree', 'sarees', 'salwar',
                          'kurti', 'kurtas', 'lehenga', 'gown', 'gowns',
                          'cloth', 'cloths', 'clothes', 'blouse', 'skirt',
                          'leggings', 'dupatta'),
    'Watches': ('watch', 'watches', 'smartwatch', 'smartwatches',
                'chronograph', 'wristwatch'),
    'Bags & Luggage': ('bag', 'bags', 'backpack', 'backpacks', 'luggage',
                       'handbag', 'handbags', 'suitcase', 'trolley',
                       'rucksack', 'tote', 'duffel'),
    'Books & Stationery': ('book', 'books', 'novel', 'novels', 'stationery',
                           'pen', 'pens', 'pencil', 'pencils', 'notebook',
                           'notebooks', 'marker', 'copy', 'copies'),
    'Grocery & Snacks': ('grocery', 'snack', 'snacks', 'food', 'biscuit',
                         'biscuits', 'chips', 'cookie', 'cookies', 'oil',
                         'masala', 'rice', 'pulses', 'dry fruits', 'tea',
                         'coffee', 'namkeen'),
    'Sports & Fitness': ('sport', 'sports', 'fitness', 'gym', 'cricket',
                         'bat', 'ball', 'badminton', 'yoga', 'dumbbell',
                         'skipping', 'football', 'basketball', 'tennis'),
    'Home & Kitchen': ('home', 'kitchen', 'cookware', 'utensils', 'kadai',
                       'tawa', 'cooker', 'juicer', 'mixer', 'blender',
                       'storage', 'curtain', 'bedsheet', 'towels', 'flask'),
    'Beauty & Personal Care': ('beauty', 'cosmetic', 'cosmetics', 'skincare',
                               'skin care', 'face wash', 'cream', 'serum',
                               'perfume', 'perfumes', 'fragrance',
                               'lipstick', 'makeup', 'hair oil', 'shampoo'),
    'Toys & Baby': ('toy', 'toys', 'baby', 'kids', 'puzzle', 'blocks',
                    'teddy', 'doll', 'rc car', 'learning'),
    'Furniture': ('furniture', 'chair', 'chairs', 'table', 'tables', 'sofa',
                  'sofas', 'desk', 'desks', 'bed', 'wardrobe', 'bookshelf'),
    'Health & Wellness': ('health', 'wellness', 'supplement', 'supplements',
                          'vitamin', 'vitamins', 'protein', 'ayurvedic',
                          'mask'),
    'Office Supplies': ('office', 'files', 'stapler', 'paper', 'folders',
                        'pins', 'calculator'),
    'Garden & Outdoor': ('garden', 'plant', 'plants', 'seed', 'seeds', 'pot',
                         'pots', 'outdoor', 'watering'),
    'Cameras & Photography': ('camera', 'cameras', 'photography', 'dslr',
                              'lens', 'tripod', 'action cam', 'gopro'),
    'Video Games & Consoles': ('game', 'games', 'gaming', 'console',
                               'playstation', 'xbox', 'controller',
                               'nintendo'),
    'Musical Instruments': ('music', 'musical', 'instrument', 'instruments',
                            'guitar', 'guitars', 'keyboard', 'piano',
                            'violin', 'drums', 'flute'),
    'Automotive Accessories': ('automotive', 'car', 'cars', 'bike', 'bikes',
                               'vehicle', 'helmet', 'seat cover',
                               'steering'),
    'Pet Supplies': ('pet', 'pets', 'dog', 'cat', 'aquarium', 'bird',
                     'leash', 'pet food'),
    'Jewellery': ('jewellery', 'jewelry', 'ring', 'rings', 'necklace',
                  'chain', 'bracelet', 'earring', 'bangle'),
    'Travel & Adventure': ('travel', 'adventure', 'suitcase', 'trolley',
                           'camping', 'tent', 'hiking', 'duffel'),
}

CHEAP_LIMIT = 1000.0


def clean_token(word):
    word = str(word).lower().strip()
    return re.sub(r'[^a-z0-9]+', '', word)


def tokenize(text):
    return [clean_token(w) for w in re.split(r'\s+', str(text).lower().strip()) if w]


def is_stopword(token):
    return token in STOPWORDS


def singular(word):
    if len(word) <= 3:
        return word
    if word.endswith('ies') and len(word) > 4:
        return word[:-3] + 'y'
    if word.endswith('sses'):
        return word[:-2]
    if word.endswith('es') and len(word) > 4:
        return word[:-2]
    if word.endswith('s') and not word.endswith(('ss', 'us', 'is')):
        return word[:-1]
    return word


def variants(word):
    forms = {word}
    forms.add(singular(word))
    if not word.endswith('s') and len(word) > 1:
        forms.add(word + 's')
    forms.update(SYNONYMS.get(word, ()))
    return tuple(f for f in forms if f)


def parse_price(query):
    text = ' ' + re.sub(r'\s+', ' ', str(query).lower()) + ' '
    price = {'low': None, 'high': None, 'around': None, 'cheap': False}

    between = re.search(
        r'\bbetween\s+' + _MONEY + _PRICE_NUM +
        r'\s*(?:and|to|-)\s*' + _MONEY + _PRICE_NUM + r'\b', text)
    if between:
        nums = re.findall(r'\d{1,7}(?:[.,]\d{1,2})?', between.group(0))
        if len(nums) >= 2:
            lo = float(re.sub(r'[^\d.]', '', nums[0]) or 0)
            hi = float(re.sub(r'[^\d.]', '', nums[1]) or 0)
            price['low'], price['high'] = sorted((lo, hi))

    under = re.search(
        r'\b(?:under|below|beneath|within|less\s+than|cheaper\s+than|upto|'
        r'up\s+to|max|maximum|at\s+most)\s+' + _MONEY + _PRICE_NUM + r'\b',
        text)
    if under and price['high'] is None:
        num = re.search(_PRICE_NUM, under.group(0))
        price['high'] = float(re.sub(r'[^\d.]', '', num.group(0)))

    above = re.search(
        r'\b(?:above|over|more\s+than|at\s+least|min|minimum|'
        r'higher\s+than)\s+' + _MONEY + _PRICE_NUM + r'\b', text)
    if above and price['low'] is None:
        num = re.search(_PRICE_NUM, above.group(0))
        price['low'] = float(re.sub(r'[^\d.]', '', num.group(0)))

    around = re.search(
        r'\b(?:around|approx(?:imately)?|about|near|close\s+to)\s+'
        + _MONEY + _PRICE_NUM + r'\b', text)
    if around and price['around'] is None:
        num = re.search(_PRICE_NUM, around.group(0))
        price['around'] = float(re.sub(r'[^\d.]', '', num.group(0)))

    rs = re.search(r'\brs\.?\s*' + _PRICE_NUM + r'\b', text)
    if (rs and price['around'] is None and price['low'] is None
            and price['high'] is None):
        num = re.search(_PRICE_NUM, rs.group(0))
        price['around'] = float(re.sub(r'[^\d.]', '', num.group(0)))

    if re.search(r'\b(?:cheap|cheapest|affordable|budget|'
                 r'low\s+(?:cost|price)|economical)\b', text):
        price['cheap'] = True
    return price


def match_category(tokens, categories):
    names = [c.name for c in categories if c.name]
    name_lower = {n.lower(): n for n in names}

    for token in tokens:
        if token in name_lower:
            return name_lower[token]

    for token in tokens:
        for alias, words in CATEGORY_ALIASES.items():
            if token in words and alias.lower() in name_lower:
                return alias

    cat_words = set()
    for n in names:
        cat_words.update(tokenize(n))

    for token in tokens:
        if len(token) <= 2:
            continue
        close = difflib.get_close_matches(token, sorted(cat_words), n=1, cutoff=0.82)
        if close:
            matched = [n for n in names if close[0] in tokenize(n)]
            if len(matched) == 1:
                return matched[0]
    return None


def _brand_vocab():
    return sorted({
        v for v in
        Product.objects.filter(status=0).values_list('vendor', flat=True).distinct()
        if v
    })


def match_brand(tokens):
    vocab = _brand_vocab()
    if not vocab:
        return None
    for token in tokens:
        for b in vocab:
            if token and token in b.lower():
                return b
    lower = [b.lower() for b in vocab]
    for token in tokens:
        if len(token) <= 2:
            continue
        close = difflib.get_close_matches(token, lower, n=1, cutoff=0.8)
        if close:
            for b in vocab:
                if b.lower() == close[0]:
                    return b
    return None


def match_color(tokens):
    lookup = {}
    for color, alts in COLORS.items():
        for alt in alts:
            lookup[alt] = color
    for token in tokens:
        if token in lookup:
            return lookup[token]
    return None


def match_size(tokens):
    for token in tokens:
        t = token.lower()
        if t in SIZE_LETTERS:
            return SIZE_LETTERS[t]
        m = re.fullmatch(r'uk\s*(\d{1,2}(?:\.\d)?)', t)
        if m:
            return 'UK ' + m.group(1)
        m = re.fullmatch(r'(\d{1,3})(cm|mm|inch|inches|kg|litre|lt)', t)
        if m:
            return m.group(1) + m.group(2).upper()
        if re.fullmatch(r'[5-9]|1[0-4]', t):
            return 'UK ' + t
    return None


def detect_size(raw):
    text = ' ' + str(raw).lower() + ' '
    m = re.search(r'\buk\.?\s*(\d{1,2}(?:\.\d)?)\b', text)
    if m:
        return 'UK ' + m.group(1)
    m = re.search(r'\b(\d{1,3})\s*(cm|mm|inch|inches|kg|litre|lt)\b', text)
    if m:
        return m.group(1) + m.group(2).upper()
    return None


def match_gender(tokens):
    for token in tokens:
        if token in GENDERS:
            return GENDERS[token]
    return None


def parse_query(query):
    raw = (query or '').strip()
    price = parse_price(raw)
    tokens = [TYPO_FIXES.get(t, t) for t in tokenize(raw)]
    tokens = [t for t in tokens if t and not is_stopword(t) and len(t) > 1]

    categories = list(Catagory.objects.filter(status=0))
    category = match_category(tokens, categories)
    brand = match_brand(tokens)
    color = match_color(tokens)
    size = match_size(tokens) or detect_size(raw)
    gender = match_gender(tokens)

    used = set()
    if category:
        used.update(tokenize(category))
    if brand:
        used.add(brand.lower())
    if color:
        used.update(COLORS[color])
    if size:
        used.add(size.lower())
        used.add(size.lower().replace(' ', ''))
        if size.startswith('UK '):
            used.add('uk')
    if gender:
        used.add(gender.lower())

    keywords = [
        t for t in tokens
        if t not in used and t not in GENERIC_WORDS and not t.isdigit()
    ]

    return {
        'query': raw,
        'price': price,
        'category': category,
        'brand': brand,
        'color': color,
        'size': size,
        'gender': gender,
        'keywords': keywords,
        'tokens': tokens,
    }


def size_search_terms(size):
    s = size.lower()
    if size.startswith('UK '):
        num = size.split(' ', 1)[1]
        return ('(uk ' + num + ')', 'uk ' + num, '(uk' + num + ')', 'uk' + num)
    return ('(' + s + ')', ' ' + s + ',', '-' + s + '-')


def _keyword_q(keywords):
    combined = Q()
    for kw in keywords:
        kw_q = Q()
        for v in variants(kw):
            kw_q |= Q(name__icontains=v) | Q(description__icontains=v)
        combined &= kw_q
    return combined


def apply_price(qs, price):
    low = price.get('low')
    high = price.get('high')
    around = price.get('around')
    applied = low is not None or high is not None or price.get('cheap')
    if price.get('cheap') and high is None:
        high = CHEAP_LIMIT
        applied = True
    if around is not None:
        low = min(low, around * 0.85) if low is not None else around * 0.85
        high = max(high, around * 1.15) if high is not None else around * 1.15
        applied = True
    if low is not None:
        qs = qs.filter(selling_price__gte=low)
    if high is not None:
        qs = qs.filter(selling_price__lte=high)
    return qs, applied


def _hard_filter(parsed, scope_category=None, min_price='', max_price=''):
    price = dict(parsed['price'])
    if min_price:
        try:
            price['low'] = float(min_price)
        except (TypeError, ValueError):
            pass
    if max_price:
        try:
            price['high'] = float(max_price)
        except (TypeError, ValueError):
            pass

    qs = Product.objects.filter(status=0)
    has_filter = False
    if scope_category:
        qs = qs.filter(category__name=scope_category)
        has_filter = True
    qs, applied = apply_price(qs, price)
    has_filter = has_filter or applied
    if parsed['category']:
        qs = qs.filter(category__name__iexact=parsed['category'])
        has_filter = True
    if parsed['brand']:
        qs = qs.filter(vendor__icontains=parsed['brand'])
        has_filter = True
    return qs, has_filter


def _soft_q(parsed):
    parts = []
    if parsed['color']:
        color_q = Q()
        for alt in COLORS[parsed['color']]:
            color_q |= Q(name__icontains=alt) | Q(description__icontains=alt)
        parts.append(color_q)
    if parsed['size']:
        size_q = Q()
        for term in size_search_terms(parsed['size']):
            size_q |= Q(name__icontains=term)
        parts.append(size_q)
    if parsed['gender']:
        hint = GENDER_CATEGORY_HINT[parsed['gender']]
        gender_q = Q()
        for word in hint:
            gender_q |= Q(category__name__icontains=word)
        parts.append(gender_q)
    if parsed['keywords']:
        parts.append(_keyword_q(parsed['keywords']))
    if not parts:
        return Q()
    combined = parts[0]
    for part in parts[1:]:
        combined &= part
    return combined


def relax_keywords(keywords, sample_size=1000):
    if not keywords:
        return keywords
    names = list(
        Product.objects.filter(status=0).values_list('name', flat=True)[:sample_size]
    )
    vocab = set()
    for name in names:
        vocab.update(tokenize(name))
    vocab = sorted(w for w in vocab if len(w) >= 3)
    corrected = []
    for kw in keywords:
        close = difflib.get_close_matches(kw, vocab, n=1, cutoff=0.75)
        corrected.append(close[0] if close else kw)
    return corrected


def score_product(product, parsed, around=None):
    name = (product.name or '').lower()
    desc = (product.description or '').lower()
    cat = (product.category.name or '').lower()
    vendor = (product.vendor or '').lower()
    score = 0.0

    if parsed['category']:
        score += 30 if cat == parsed['category'].lower() else 18

    if parsed['brand'] and parsed['brand'].lower() in vendor:
        score += 25

    if parsed['gender']:
        if parsed['gender'].lower() in cat:
            score += 15
        elif any(h in name for h in GENDER_CATEGORY_HINT[parsed['gender']]):
            score += 6

    if parsed['color'] and parsed['color'].lower() in name:
        score += 15

    if parsed['size'] and any(t in name for t in size_search_terms(parsed['size'])):
        score += 12

    for kw in parsed['keywords']:
        kw_variants = variants(kw)
        if any(v in name for v in kw_variants):
            score += 10
        elif any(v in desc for v in kw_variants):
            score += 4
        if any(w.startswith(kw) for w in name.split()):
            score += 2

    if parsed['query'].lower() in name:
        score += 15

    if parsed['price'].get('cheap'):
        if product.selling_price <= CHEAP_LIMIT:
            score += 3

    if around:
        diff = abs(product.selling_price - around)
        score -= min(diff / around, 1.0) * 8

    score += float(product.avg_rating or 0) * 1.5
    return score


def smart_search(query, scope_category=None, sort_by='', min_price='',
                 max_price='', rank_limit=800):
    parsed = parse_query(query)
    hard, has_hard = _hard_filter(parsed, scope_category, min_price, max_price)

    soft_q = _soft_q(parsed)
    results = hard.filter(soft_q) if parsed['keywords'] or soft_q else hard

    if not results.exists() and parsed['keywords']:
        corrected = relax_keywords(parsed['keywords'])
        if corrected != parsed['keywords']:
            parsed['keywords'] = corrected
            soft_q = _soft_q(parsed)
            results = hard.filter(soft_q) if soft_q else hard

    if not results.exists():
        if has_hard:
            results = hard
        else:
            results = Product.objects.none()

    results = results.annotate(
        avg_rating=Avg('ratings__rating'),
        rating_count=Count('ratings'),
    )

    if sort_by in SORT_MAP:
        return results.order_by(SORT_MAP[sort_by]), parsed

    count = results.count()
    if 0 < count <= rank_limit:
        candidates = list(results.select_related('category').order_by('id')[:rank_limit])
        around = parsed['price'].get('around')
        candidates.sort(key=lambda p: score_product(p, parsed, around), reverse=True)
        return candidates, parsed

    return results, parsed


def related_products(parsed, exclude_ids=(), limit=8):
    base = Product.objects.filter(status=0).exclude(id__in=exclude_ids).annotate(
        avg_rating=Avg('ratings__rating'),
        rating_count=Count('ratings'),
    )

    if parsed['category']:
        return base.filter(category__name__iexact=parsed['category']).order_by(
            '-avg_rating', '-id')[:limit]
    if parsed['brand']:
        return base.filter(vendor__icontains=parsed['brand']).order_by(
            '-avg_rating', '-id')[:limit]
    if parsed['gender']:
        hint = GENDER_CATEGORY_HINT[parsed['gender']]
        gender_q = Q()
        for word in hint:
            gender_q |= Q(category__name__icontains=word)
        return base.filter(gender_q).order_by('-avg_rating', '-id')[:limit]
    for kw in parsed['keywords']:
        related = base.filter(_keyword_q([kw])).order_by('-avg_rating', '-id')[:limit]
        if related.exists():
            return related
    return base.order_by('-avg_rating', '-id')[:limit]


def build_chips(parsed):
    chips = []
    if parsed['category']:
        chips.append({'icon': 'fa-tags', 'label': 'Category', 'value': parsed['category']})
    if parsed['brand']:
        chips.append({'icon': 'fa-tag', 'label': 'Brand', 'value': parsed['brand']})
    if parsed['gender']:
        chips.append({'icon': 'fa-venus-mars', 'label': 'For', 'value': parsed['gender']})
    if parsed['color']:
        chips.append({'icon': 'fa-palette', 'label': 'Colour', 'value': parsed['color']})
    if parsed['size']:
        chips.append({'icon': 'fa-ruler', 'label': 'Size', 'value': parsed['size']})

    price = parsed['price']
    if price['cheap']:
        chips.append({'icon': 'fa-indian-rupee-sign', 'label': 'Budget',
                      'value': 'Cheap (under Rs. %d)' % CHEAP_LIMIT})
    if price['around'] is not None:
        chips.append({'icon': 'fa-indian-rupee-sign', 'label': 'Around',
                      'value': 'Rs. %d' % int(price['around'])})
    if price['low'] is not None and price['high'] is not None:
        chips.append({'icon': 'fa-indian-rupee-sign', 'label': 'Price',
                      'value': 'Rs. %d - Rs. %d' % (int(price['low']), int(price['high']))})
    elif price['low'] is not None:
        chips.append({'icon': 'fa-indian-rupee-sign', 'label': 'Min',
                      'value': 'Rs. %d+' % int(price['low'])})
    elif price['high'] is not None:
        chips.append({'icon': 'fa-indian-rupee-sign', 'label': 'Max',
                      'value': 'Under Rs. %d' % int(price['high'])})

    if parsed['keywords']:
        chips.append({'icon': 'fa-key', 'label': 'Keywords',
                      'value': ', '.join(parsed['keywords'])})
    return chips
