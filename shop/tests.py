from django.test import TestCase
from django.urls import reverse
from django.test import override_settings
from django.contrib.auth.models import User
from unittest import mock
import re

from shop.models import Catagory, Product, UserProfile


class AdminDashboardAccessTests(TestCase):
    """Accessing /dashboard/ must never flash an error just because the
    Dashboard section is unticked: with other navs the user is redirected to
    their first available page silently, and with no navs they go home."""

    @classmethod
    def setUpTestData(cls):
        cls.su = User.objects.create_superuser('boss4', 'boss4@x.com', 'pass12345')

    def _errors_in(self, response):
        html = response.content.decode('utf-8', errors='replace')
        return 'You don\'t have access to the admin dashboard' in html

    def test_with_navs_no_error_and_redirects_to_first_nav(self):
        from django.contrib.auth.models import Permission
        target = User.objects.create_user('dash1', 'dash1@x.com', is_staff=True)
        target.user_permissions.add(
            Permission.objects.get(codename='view_payment', content_type__app_label='shop'))
        self.client.force_login(target)

        resp = self.client.get('/dashboard/', HTTP_HOST='localhost')
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('admin_payments'))
        follow = self.client.get(resp.url, HTTP_HOST='localhost')
        self.assertEqual(follow.status_code, 200)
        self.assertFalse(self._errors_in(follow))

    def test_no_navs_shows_no_access_page(self):
        target = User.objects.create_user('dash2', 'dash2@x.com', is_staff=True)
        self.client.force_login(target)
        resp = self.client.get('/dashboard/', HTTP_HOST='localhost')
        self.assertEqual(resp.status_code, 403)
        html = resp.content.decode('utf-8', errors='replace')
        self.assertIn('No Access', html)
        self.assertIn('has no navigation sections', html)
        self.assertFalse(self._errors_in(resp))

    def test_no_navs_home_does_not_loop(self):
        target = User.objects.create_user('dash4', 'dash4@x.com', is_staff=True)
        self.client.force_login(target)
        resp = self.client.get('/', HTTP_HOST='localhost')
        self.assertEqual(resp.status_code, 200)
        self.assertNotEqual(resp['Location'] if resp.has_header('Location') else None, reverse('admin_dashboard'))

    def test_products_only_redirects_to_products(self):
        from django.contrib.auth.models import Permission
        target = User.objects.create_user('dash3', 'dash3@x.com', is_staff=True)
        target.user_permissions.add(
            Permission.objects.get(codename='view_product', content_type__app_label='shop'))
        self.client.force_login(target)
        resp = self.client.get('/dashboard/', HTTP_HOST='localhost')
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('admin_products'))
        follow = self.client.get(resp.url, HTTP_HOST='localhost')
        self.assertFalse(self._errors_in(follow))


class SmartSearchTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.mobiles = Catagory.objects.create(name='Mobiles', description='All mobiles')
        cls.footwear = Catagory.objects.create(name='Footwear', description='Shoes')
        cls.shirts = Catagory.objects.create(name='Shirts For Men', description='Shirts')
        cls.watches = Catagory.objects.create(name='Watches', description='Watches')
        cls.sports = Catagory.objects.create(name='Sports & Fitness', description='Sports')

        def mk(name, vendor, price, category, desc=''):
            return Product.objects.create(
                category=category, name=name, vendor=vendor, quantity=10,
                original_price=price * 2, selling_price=price,
                description=desc, status=0,
            )

        cls.iphone = mk('Apple iPhone 17 (Black, 256 GB)', 'Apple', 82900, cls.mobiles, '12 GB RAM | 5G')
        cls.poco = mk('POCO x7 Pro 5G (Black, 256 GB)', 'Poco', 23999, cls.mobiles, '12 GB RAM | 5G')
        cls.samsung = mk('Samsung Galaxy S24 (Black, 128 GB)', 'Samsung', 50999, cls.mobiles, '8 GB RAM | 5G')
        cls.cheap_phone = mk('Generic Basic Phone (Black, 32 GB)', 'Generic', 4999, cls.mobiles, '2 GB RAM')
        cls.nike_white = mk('Nike Air Max SC (White)', 'Nike', 4995, cls.footwear, 'running shoes')
        cls.nike_black = mk('Nike Air Max 270 (Black)', 'Nike', 7999, cls.footwear, 'running')
        cls.puma_white = mk('Puma Palermo Sneakers (White)', 'Puma', 3999, cls.footwear, 'sneakers')
        cls.nike_samba = mk('Nike Samba Classic (UK 7)', 'Nike', 5999, cls.footwear, 'classic shoe')
        cls.tee = mk('Nike Dri-FIT T-Shirt (M, White)', 'Nike', 899, cls.shirts, 'cotton tee')
        cls.formal = mk('Arrow Formal Shirt (M, White)', 'Arrow', 1599, cls.shirts, 'formal wear')
        cls.casual = mk('Roadster Casual Shirt (L, Blue)', 'Roadster', 999, cls.shirts, 'casual')
        cls.watch1 = mk('Casio G-Shock (Black)', 'Casio', 2499, cls.watches, 'sporty watch')
        cls.ball = mk('Wilson Football (White)', 'Wilson', 1299, cls.sports, 'sports ball')

    def search(self, q, **kwargs):
        from shop.smart_search import smart_search
        results, parsed = smart_search(q, **kwargs)
        ids = [p.id for p in (results[:50] if not hasattr(results, 'count') else results[:50])]
        return ids, parsed

    def test_category_brand_price_parse(self):
        ids, parsed = self.search('samsung phone under 30000')
        self.assertEqual(parsed['brand'], 'Samsung')
        self.assertEqual(parsed['category'], 'Mobiles')
        self.assertEqual(parsed['price']['high'], 30000)
        self.assertEqual(ids, [])

    def test_price_under(self):
        ids, _ = self.search('mobile under 20000')
        self.assertIn(self.cheap_phone.id, ids)
        self.assertNotIn(self.iphone.id, ids)

    def test_price_between(self):
        ids, parsed = self.search('watch between 1500 and 3000')
        self.assertEqual(parsed['price']['low'], 1500)
        self.assertEqual(parsed['price']['high'], 3000)
        self.assertIn(self.watch1.id, ids)

    def test_color_and_brand_filter(self):
        ids, _ = self.search('nike shoes black')
        self.assertIn(self.nike_black.id, ids)
        self.assertNotIn(self.puma_white.id, ids)

    def test_size_match(self):
        ids, parsed = self.search('nike samba uk 7')
        self.assertEqual(parsed['size'], 'UK 7')
        self.assertIn(self.nike_samba.id, ids)

    def test_synonym_tshirt(self):
        ids, _ = self.search('black tshirt')
        self.assertIn(self.tee.id, ids)

    def test_spelling_correction(self):
        ids, parsed = self.search('nike shrit')
        self.assertIn(self.tee.id, ids)

    def test_relaxed_spelling(self):
        ids, _ = self.search('puma sneekers')
        self.assertIn(self.puma_white.id, ids)

    def test_gibberish_returns_nothing(self):
        ids, _ = self.search('zzzqqq unknown words')
        self.assertEqual(ids, [])

    def test_related_fallback(self):
        from shop.smart_search import parse_query, related_products
        parsed = parse_query('zzzqqq unknown words')
        related = related_products(parsed, limit=5)
        self.assertTrue(related.exists())

    def test_relevance_ranking_nike_first(self):
        ids, _ = self.search('running shoes nike')
        self.assertIn(self.nike_white.id, ids)
        self.assertIn(self.nike_black.id, ids)
        self.assertNotIn(self.puma_white.id, ids)
        self.assertLess(ids.index(self.nike_white.id), ids.index(self.nike_black.id))

    def test_graceful_degradation(self):
        ids, parsed = self.search('nike shoes red')
        self.assertEqual(parsed['brand'], 'Nike')
        self.assertIn(self.nike_white.id, ids)

    def test_search_view_renders(self):
        resp = self.client.get(reverse('search'), {'q': 'nike shoes black'})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Nike')
        self.assertContains(resp, 'AI understood')

    def test_search_view_related_empty(self):
        resp = self.client.get(reverse('search'), {'q': 'zzzqqq unknown'})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'related products')

    def test_autocomplete_returns_json(self):
        resp = self.client.get(reverse('search_autocomplete'), {'q': 'nike'})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(len(data) > 0)


GOOGLE_CLIENT_ID_TEST = 'test-client.apps.googleusercontent.com'


class GoogleAuthTests(TestCase):

    @override_settings(GOOGLE_CLIENT_ID=GOOGLE_CLIENT_ID_TEST, GOOGLE_CLIENT_SECRET='test-secret')
    def test_login_page_renders_with_google_button(self):
        resp = self.client.get(reverse('login'), HTTP_HOST='127.0.0.1')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'auth-divider')
        self.assertContains(resp, 'Continue with Google')
        self.assertContains(resp, reverse('google_login'))

    def test_google_auth_get_rejected(self):
        resp = self.client.get(reverse('google_auth'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {'ok': False, 'error': 'Invalid request.'})

    def test_google_auth_missing_credential(self):
        resp = self.client.post(reverse('google_auth'), {'credential': ''})
        data = resp.json()
        self.assertFalse(data['ok'])
        self.assertIn('cancelled', data['error'])

    @override_settings(GOOGLE_CLIENT_ID='')
    def test_google_auth_not_configured(self):
        resp = self.client.post(reverse('google_auth'), {'credential': 'abc.def.ghi'})
        data = resp.json()
        self.assertFalse(data['ok'])
        self.assertIn('not configured', data['error'])

    @override_settings(GOOGLE_CLIENT_ID=GOOGLE_CLIENT_ID_TEST)
    @mock.patch('shop.views.fetch_gravatar', return_value=None)
    @mock.patch('shop.views.fetch_google_picture', return_value=None)
    def test_google_auth_creates_and_logs_in_user(self, _pic, _gravatar):
        session = self.client.session
        session['google_auth_nonce'] = 'testnonce'
        session.save()

        idinfo = {
            'iss': 'https://accounts.google.com',
            'aud': GOOGLE_CLIENT_ID_TEST,
            'nonce': 'testnonce',
            'email': 'john.doe@gmail.com',
            'email_verified': True,
            'name': 'John Doe',
            'picture': 'https://example.com/pic.jpg',
            'sub': 'google-uid-123',
        }
        with mock.patch('google.oauth2.id_token.verify_oauth2_token', return_value=idinfo):
            resp = self.client.post(reverse('google_auth'), {'credential': 'fake.jwt.token'})

        self.assertEqual(resp.json(), {'ok': True})
        user = User.objects.get(email__iexact='john.doe@gmail.com')
        self.assertEqual(int(self.client.session['_auth_user_id']), user.pk)
        self.assertEqual(user.first_name, 'John')
        self.assertEqual(user.last_name, 'Doe')
        self.assertTrue(UserProfile.objects.filter(user=user).exists())

    @override_settings(GOOGLE_CLIENT_ID=GOOGLE_CLIENT_ID_TEST)
    def test_google_auth_rejects_bad_nonce(self):
        session = self.client.session
        session['google_auth_nonce'] = 'expected-nonce'
        session.save()

        idinfo = {
            'iss': 'https://accounts.google.com',
            'aud': GOOGLE_CLIENT_ID_TEST,
            'nonce': 'wrong-nonce',
            'email': 'attacker@gmail.com',
            'email_verified': True,
            'name': 'Attacker',
        }
        with mock.patch('google.oauth2.id_token.verify_oauth2_token', return_value=idinfo):
            resp = self.client.post(reverse('google_auth'), {'credential': 'fake.jwt.token'})

        data = resp.json()
        self.assertFalse(data['ok'])
        self.assertIn('Security check', data['error'])
        self.assertFalse(User.objects.filter(email__iexact='attacker@gmail.com').exists())

    @override_settings(GOOGLE_CLIENT_ID=GOOGLE_CLIENT_ID_TEST)
    def test_google_auth_rejects_unverified_email(self):
        session = self.client.session
        session['google_auth_nonce'] = 'expected-nonce'
        session.save()

        idinfo = {
            'iss': 'https://accounts.google.com',
            'aud': GOOGLE_CLIENT_ID_TEST,
            'nonce': 'expected-nonce',
            'email': 'unverified@gmail.com',
            'email_verified': False,
            'name': 'No Verify',
        }
        with mock.patch('google.oauth2.id_token.verify_oauth2_token', return_value=idinfo):
            resp = self.client.post(reverse('google_auth'), {'credential': 'fake.jwt.token'})

        data = resp.json()
        self.assertFalse(data['ok'])
        self.assertIn('verify your email', data['error'])
        self.assertFalse(User.objects.filter(email__iexact='unverified@gmail.com').exists())

    @override_settings(GOOGLE_CLIENT_ID=GOOGLE_CLIENT_ID_TEST)
    def test_google_auth_existing_user_by_email(self):
        existing = User.objects.create_user(
            username='already@example.com', email='already@example.com', first_name='Old'
        )
        session = self.client.session
        session['google_auth_nonce'] = 'expected-nonce'
        session.save()

        idinfo = {
            'iss': 'accounts.google.com',
            'aud': GOOGLE_CLIENT_ID_TEST,
            'nonce': 'expected-nonce',
            'email': 'ALREADY@example.com',
            'email_verified': True,
            'name': 'New Name',
        }
        with mock.patch('google.oauth2.id_token.verify_oauth2_token', return_value=idinfo):
            with mock.patch('shop.views.fetch_gravatar', return_value=None):
                resp = self.client.post(reverse('google_auth'), {'credential': 'fake.jwt.token'})

        self.assertEqual(resp.json(), {'ok': True})
        self.assertEqual(User.objects.filter(email__iexact='already@example.com').count(), 1)
        self.assertEqual(User.objects.get(pk=existing.pk).first_name, 'Old')

    @override_settings(GOOGLE_CLIENT_ID=GOOGLE_CLIENT_ID_TEST, GOOGLE_CLIENT_SECRET='test-secret')
    def test_google_login_redirects_to_google(self):
        resp = self.client.get(reverse('google_login'), HTTP_HOST='127.0.0.1')
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(resp.url.startswith('https://accounts.google.com/o/oauth2/v2/auth'))
        self.assertIn('client_id=' + GOOGLE_CLIENT_ID_TEST, resp.url)
        self.assertIn('response_type=code', resp.url)
        self.assertIn('redirect_uri=', resp.url)
        self.assertIn('state=', resp.url)

    @override_settings(
        DEBUG=False,
        GOOGLE_CLIENT_ID=GOOGLE_CLIENT_ID_TEST,
        GOOGLE_CLIENT_SECRET='test-secret',
        SITE_DOMAIN='kavibazaar-production.up.railway.app',
        ALLOWED_HOSTS=[
            'weatherapprender-production.up.railway.app',
            'kavibazaar-production.up.railway.app',
            'testserver',
        ],
        SECURE_SSL_REDIRECT=False,
    )
    def test_google_login_uses_site_domain_for_redirect_uri(self):
        # Even when the request arrives through a stale/old host header, the
        # redirect_uri sent to Google must be the current SITE_DOMAIN over
        # https, with no trailing slash after 'callback'.
        resp = self.client.get(
            reverse('google_login'),
            HTTP_HOST='weatherapprender-production.up.railway.app')
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(resp.url.startswith('https://accounts.google.com/o/oauth2/v2/auth'))
        self.assertIn(
            'redirect_uri=https%3A%2F%2Fkavibazaar-production.up.railway.app%2Fgoogle-auth%2Fcallback',
            resp.url,
        )
        self.assertNotIn('weatherapprender', resp.url)

    @override_settings(GOOGLE_CLIENT_ID='', GOOGLE_CLIENT_SECRET='')
    def test_google_login_not_configured(self):
        resp = self.client.get(reverse('google_login'))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('login'))

    @override_settings(GOOGLE_CLIENT_ID=GOOGLE_CLIENT_ID_TEST, GOOGLE_CLIENT_SECRET='test-secret')
    def test_google_callback_rejects_state_mismatch(self):
        session = self.client.session
        session['google_oauth_state'] = 'expected-state'
        session['google_oauth_next'] = '/'
        session.save()
        resp = self.client.get(
            reverse('google_callback'), {'code': 'abc', 'state': 'wrong'},
            HTTP_HOST='127.0.0.1')
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('login'))
        self.assertFalse(User.objects.filter(email__iexact='anyone@gmail.com').exists())

    @override_settings(GOOGLE_CLIENT_ID=GOOGLE_CLIENT_ID_TEST, GOOGLE_CLIENT_SECRET='test-secret')
    @mock.patch('shop.views.fetch_gravatar', return_value=None)
    @mock.patch('shop.views.fetch_google_picture', return_value=None)
    def test_google_callback_logs_in_user(self, _pic, _gravatar):
        session = self.client.session
        session['google_oauth_state'] = 'expected-state'
        session['google_oauth_next'] = '/profile'
        session.save()

        idinfo = {
            'iss': 'https://accounts.google.com',
            'aud': GOOGLE_CLIENT_ID_TEST,
            'email': 'oauth.user@gmail.com',
            'email_verified': True,
            'name': 'OAuth User',
            'sub': 'oauth-uid-1',
        }
        with mock.patch('shop.views._google_exchange_code', return_value={'id_token': 'fake.jwt'}):
            with mock.patch('google.oauth2.id_token.verify_oauth2_token', return_value=idinfo):
                resp = self.client.get(
                    reverse('google_callback'), {'code': 'abc', 'state': 'expected-state'},
                    HTTP_HOST='127.0.0.1')

        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, '/profile')
        user = User.objects.get(email__iexact='oauth.user@gmail.com')
        self.assertEqual(int(self.client.session['_auth_user_id']), user.pk)
        self.assertEqual(user.first_name, 'OAuth')
        self.assertEqual(user.last_name, 'User')


class SuperuserAdminTests(TestCase):
    """The admin user-change page must save superuser status from either the
    built-in 'Superuser status' checkbox or the custom nav 'Permissions'
    checkbox, and must not revert the other."""

    @classmethod
    def setUpTestData(cls):
        cls.su = User.objects.create_superuser('boss', 'boss@x.com', 'pass12345')

    def setUp(self):
        self.client.force_login(self.su)

    def _change_url(self, target):
        return reverse('admin:auth_user_change', args=[target.pk])

    def _post(self, target, section_permissions):
        url = self._change_url(target)
        resp = self.client.get(url, HTTP_HOST='localhost')
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode('utf-8', errors='replace')
        form = re.search(r'<form[^>]*id="user_form"[^>]*>(.*?)</form>', html, re.S).group(1)

        post = {}
        for m in re.finditer(r'<input[^>]*name="([^"]+)"[^>]*>', form):
            name = m.group(1)
            tag = m.group(0)
            typ = re.search(r'type="([^"]+)"', tag)
            typ = typ.group(1) if typ else 'text'
            if typ == 'checkbox':
                post.setdefault(name, [])
            elif typ == 'submit' or typ == 'file':
                continue
            else:
                val = re.search(r'value="([^"]*)"', tag)
                post[name] = val.group(1) if val else ''
        for m in re.finditer(r'<select[^>]*name="([^"]+)"[^>]*>', form):
            post.setdefault(m.group(1), [])
        for m in re.finditer(r'<textarea[^>]*name="([^"]+)"[^>]*>', form):
            post.setdefault(m.group(1), '')

        post['section_permissions'] = ['on'] if section_permissions else []
        return self.client.post(url, post, HTTP_HOST='localhost')

    def test_nav_permissions_checkbox_saves_superuser(self):
        target = User.objects.create_user('target1', 't1@x.com', is_staff=True)
        self._post(target, section_permissions=True)
        target.refresh_from_db()
        self.assertTrue(target.is_superuser)

    def test_unchecked_stays_non_superuser(self):
        target = User.objects.create_user('target2', 't2@x.com', is_staff=True)
        self._post(target, section_permissions=False)
        target.refresh_from_db()
        self.assertFalse(target.is_superuser)

    def test_superuser_status_field_removed(self):
        target = User.objects.create_user('target3', 't3@x.com', is_staff=True)
        resp = self.client.get(self._change_url(target), HTTP_HOST='localhost')
        html = resp.content.decode('utf-8', errors='replace')
        self.assertNotIn('id_is_superuser', html)
        self.assertNotIn('Designates that this user has all permissions', html)


class AdminNavSectionSaveTests(TestCase):
    """Every Admin Navigation Access checkbox on the Django admin change page
    must persist (grant + revoke + reload)."""

    @classmethod
    def setUpTestData(cls):
        cls.su = User.objects.create_superuser('boss3', 'boss3@x.com', 'pass12345')

    def setUp(self):
        self.client.force_login(self.su)

    SECTION_KEYS = [
        'section_dashboard', 'section_products', 'section_categories',
        'section_orders', 'section_payments', 'section_reviews',
        'section_low_stock', 'section_send_announcement', 'section_permissions',
    ]

    def _change_url(self, target):
        return reverse('admin:auth_user_change', args=[target.pk])

    def _checked_state(self, target):
        resp = self.client.get(self._change_url(target), HTTP_HOST='localhost')
        html = resp.content.decode('utf-8', errors='replace')
        form = re.search(r'<form[^>]*id="user_form"[^>]*>(.*?)</form>', html, re.S).group(1)
        state = {}
        for key in self.SECTION_KEYS:
            m = re.search(r'<input[^>]*name="%s"[^>]*>' % re.escape(key), form)
            state[key] = bool(m and 'checked' in m.group(0))
        return state

    def _build_post(self, target):
        resp = self.client.get(self._change_url(target), HTTP_HOST='localhost')
        html = resp.content.decode('utf-8', errors='replace')
        form = re.search(r'<form[^>]*id="user_form"[^>]*>(.*?)</form>', html, re.S).group(1)
        post = {}
        for m in re.finditer(r'<input[^>]*name="([^"]+)"[^>]*>', form):
            name = m.group(1)
            tag = m.group(0)
            typ = re.search(r'type="([^"]+)"', tag)
            typ = typ.group(1) if typ else 'text'
            if typ == 'checkbox':
                post.setdefault(name, [])
            elif typ in ('submit', 'file'):
                continue
            else:
                val = re.search(r'value="([^"]*)"', tag)
                post[name] = val.group(1) if val else ''
        for m in re.finditer(r'<select[^>]*name="([^"]+)"[^>]*>', form):
            post.setdefault(m.group(1), [])
        for m in re.finditer(r'<textarea[^>]*name="([^"]+)"[^>]*>', form):
            post.setdefault(m.group(1), '')
        return post

    def test_all_sections_save_and_reload(self):
        target = User.objects.create_user('nav1', 'nav1@x.com', is_staff=True)
        post = self._build_post(target)
        for key in self.SECTION_KEYS:
            post[key] = ['on']
        self.client.post(self._change_url(target), post, HTTP_HOST='localhost')

        target.refresh_from_db()
        codes = set(target.user_permissions.filter(
            content_type__app_label='shop').values_list('codename', flat=True))
        self.assertIn('view_product', codes)
        self.assertIn('view_catagory', codes)
        self.assertIn('view_order', codes)
        self.assertIn('view_payment', codes)
        self.assertIn('view_productrating', codes)
        self.assertIn('change_notification', codes)
        self.assertTrue(target.is_superuser)

        state = self._checked_state(target)
        for key in self.SECTION_KEYS:
            self.assertTrue(state[key], '%s should be checked after save' % key)

    def test_clear_all_sections(self):
        target = User.objects.create_user('nav2', 'nav2@x.com', is_staff=True)
        post = self._build_post(target)
        for key in self.SECTION_KEYS:
            post[key] = ['on']
        self.client.post(self._change_url(target), post, HTTP_HOST='localhost')

        post = self._build_post(target)
        for key in self.SECTION_KEYS:
            post[key] = []
        self.client.post(self._change_url(target), post, HTTP_HOST='localhost')

        target.refresh_from_db()
        codes = set(target.user_permissions.filter(
            content_type__app_label='shop').values_list('codename', flat=True))
        self.assertEqual(codes, set())
        self.assertFalse(target.is_superuser)
        state = self._checked_state(target)
        for key in self.SECTION_KEYS:
            self.assertFalse(state[key], '%s should be unchecked after clearing' % key)


class StaffPermissionsPageTests(TestCase):
    """The custom /dashboard/staff-permissions/ page must save every section
    checkbox it renders (products, categories, orders, payments, reviews,
    low_stock, send_announcement) and keep shared permissions working."""

    @classmethod
    def setUpTestData(cls):
        cls.su = User.objects.create_superuser('boss2', 'boss2@x.com', 'pass12345')

    def setUp(self):
        self.client.force_login(self.su)

    def test_grants_checked_sections(self):
        target = User.objects.create_user('perm1', 'perm1@x.com', is_staff=True)
        url = reverse('admin_staff_permissions')
        post = {
            'section_%d_dashboard' % target.id: 'on',
            'section_%d_products' % target.id: 'on',
            'section_%d_payments' % target.id: 'on',
            'section_%d_reviews' % target.id: 'on',
        }
        resp = self.client.post(url, post, HTTP_HOST='localhost')
        self.assertEqual(resp.status_code, 302)
        target.refresh_from_db()
        codes = set(target.user_permissions.filter(
            content_type__app_label='shop').values_list('codename', flat=True))
        self.assertIn('view_product', codes)
        self.assertIn('view_payment', codes)
        self.assertIn('view_productrating', codes)
        self.assertNotIn('view_catagory', codes)

    def test_reviews_and_low_stock_checkboxes_render(self):
        target = User.objects.create_user('perm2', 'perm2@x.com', is_staff=True)
        resp = self.client.get(reverse('admin_staff_permissions'), HTTP_HOST='localhost')
        html = resp.content.decode('utf-8', errors='replace')
        self.assertIn('section_%d_reviews' % target.id, html)
        self.assertIn('section_%d_payments' % target.id, html)
        self.assertIn('section_%d_low_stock' % target.id, html)
        self.assertIn('section_%d_send_announcement' % target.id, html)

    def _post_sections(self, target, on_keys):
        post = {}
        for key in ('dashboard', 'products', 'categories', 'orders', 'payments',
                    'reviews', 'low_stock', 'send_announcement'):
            if key in on_keys:
                post['section_%d_%s' % (target.id, key)] = 'on'
        return self.client.post(reverse('admin_staff_permissions'), post, HTTP_HOST='localhost')

    def test_untick_removes_permissions(self):
        target = User.objects.create_user('perm3', 'perm3@x.com', is_staff=True)
        url = reverse('admin_staff_permissions')

        self._post_sections(target, ['products', 'categories', 'orders', 'payments',
                                     'reviews', 'low_stock', 'send_announcement'])
        target.refresh_from_db()
        codes = set(target.user_permissions.filter(
            content_type__app_label='shop').values_list('codename', flat=True))
        self.assertIn('view_product', codes)
        self.assertIn('view_catagory', codes)
        self.assertIn('view_order', codes)
        self.assertIn('view_payment', codes)
        self.assertIn('view_productrating', codes)
        self.assertIn('change_notification', codes)

        # Untick ONLY products -> view_product must go, others stay
        self._post_sections(target, ['categories', 'orders', 'payments', 'reviews',
                                     'low_stock', 'send_announcement'])
        target.refresh_from_db()
        codes = set(target.user_permissions.filter(
            content_type__app_label='shop').values_list('codename', flat=True))
        self.assertNotIn('view_product', codes)
        self.assertIn('view_catagory', codes)
        self.assertIn('view_payment', codes)
        self.assertIn('change_notification', codes)

        # Untick everything -> all shop perms gone
        self._post_sections(target, [])
        target.refresh_from_db()
        codes = set(target.user_permissions.filter(
            content_type__app_label='shop').values_list('codename', flat=True))
        self.assertEqual(codes, set())

    def test_untick_all_keeps_user_listed(self):
        target = User.objects.create_user('perm4', 'perm4@x.com', is_staff=True)
        url = reverse('admin_staff_permissions')
        self._post_sections(target, ['products'])
        self._post_sections(target, [])

        target.refresh_from_db()
        self.assertTrue(target.is_staff)

        resp = self.client.get(url, HTTP_HOST='localhost')
        html = resp.content.decode('utf-8', errors='replace')
        self.assertIn('section_%d_products' % target.id, html)
        self.assertIn('perm4', html)
