import tempfile
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree

from django.conf import settings
from django.contrib.staticfiles import finders
from django.core.management import call_command
from django.template.loader import render_to_string
from django.templatetags.static import static
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

BRAND_ASSET = "branding/open-book.svg"


class BrandMarkupParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.icons = []
        self.logos = []
        self.home_links = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        classes = attributes.get("class", "").split()
        if tag == "link" and attributes.get("rel") == "icon":
            self.icons.append(attributes)
        if tag == "img" and "brand__logo" in classes:
            self.logos.append(attributes)
        if tag == "a" and "brand" in classes:
            self.home_links.append(attributes)


class BrandAssetTests(SimpleTestCase):
    def test_selected_icon_is_a_local_square_svg(self):
        path = finders.find(BRAND_ASSET)
        self.assertIsNotNone(path)
        root = ElementTree.parse(path).getroot()
        self.assertEqual(root.tag, "{http://www.w3.org/2000/svg}svg")
        self.assertEqual(root.attrib["viewBox"], "0 0 24 24")
        self.assertTrue(root.findall("{http://www.w3.org/2000/svg}path"))
        self._assert_self_contained(root)

    def _assert_self_contained(self, root):
        for element in root.iter():
            self.assertNotIn(
                element.tag.rsplit("}", 1)[-1],
                {"script", "image", "foreignObject", "text"},
            )
            for name, value in element.attrib.items():
                self.assertFalse(name.lower().startswith("on"))
                self.assertNotIn("href", name.lower())
                self.assertNotIn("url(", value.lower())


class BrandTemplateTests(SimpleTestCase):
    def _markup(self, template="base.html"):
        parser = BrandMarkupParser()
        parser.feed(render_to_string(template))
        return parser

    def test_favicon_and_header_use_the_same_selected_image(self):
        markup = self._markup()
        self.assertEqual(len(markup.icons), 1)
        self.assertEqual(len(markup.logos), 1)
        self.assertEqual(markup.icons[0]["type"], "image/svg+xml")
        self.assertEqual(markup.icons[0]["sizes"], "any")
        self.assertEqual(markup.icons[0]["href"], static(BRAND_ASSET))
        self.assertEqual(markup.logos[0]["src"], markup.icons[0]["href"])

    def test_logo_has_fixed_dimensions_without_repeating_the_link_name(self):
        markup = self._markup()
        self.assertEqual(len(markup.logos), 1)
        self.assertEqual(markup.logos[0]["width"], "32")
        self.assertEqual(markup.logos[0]["height"], "32")
        self.assertEqual(markup.logos[0]["alt"], "")
        self.assertEqual(markup.home_links[0]["href"], reverse("book-list"))
        self.assertIn("<span>Library</span>", render_to_string("base.html"))

    def test_login_inherits_the_same_brand(self):
        markup = self._markup("registration/login.html")
        self.assertEqual(len(markup.icons), 1)
        self.assertEqual(len(markup.logos), 1)
        self.assertEqual(markup.icons[0]["href"], static(BRAND_ASSET))
        self.assertEqual(markup.icons[0]["href"], markup.logos[0]["src"])

    def test_manifest_storage_keeps_favicon_and_logo_in_sync(self):
        storages = {
            **settings.STORAGES,
            "staticfiles": {
                "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
            },
        }
        with tempfile.TemporaryDirectory() as root:
            with override_settings(DEBUG=False, STATIC_ROOT=root, STORAGES=storages):
                call_command("collectstatic", interactive=False, verbosity=0)
                markup = self._markup()
                asset_url = static(BRAND_ASSET)
                self.assertEqual(len(markup.icons), 1)
                self.assertEqual(len(markup.logos), 1)
                self.assertNotEqual(asset_url, "/static/" + BRAND_ASSET)
                self.assertEqual(markup.icons[0]["href"], asset_url)
                self.assertEqual(markup.logos[0]["src"], asset_url)
                self.assertTrue((Path(root) / asset_url.removeprefix("/static/")).is_file())


class HomepageBrandTests(TestCase):
    def test_public_homepage_displays_the_selected_brand(self):
        response = self.client.get(reverse("book-list"))
        self.assertContains(response, 'class="brand__logo"')
        self.assertContains(response, static(BRAND_ASSET), count=2)
        self.assertContains(response, "<h1>Books</h1>", html=True)
