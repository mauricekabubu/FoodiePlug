from django.conf import settings
from django.contrib.sitemaps import Sitemap
from django.urls import reverse


class PublicPagesSitemap(Sitemap):
    protocol = "https"
    changefreq = "monthly"
    priority = 0.8

    public_pages = [
        ("intro", 1.0),
        ("terms", 0.3),
        ("privacy", 0.3),
        ("contact", 0.6),
    ]

    def items(self):
        return [name for name, _priority in self.public_pages]

    def location(self, item):
        return reverse(item)

    def priority(self, item):
        return dict(self.public_pages)[item]

    def get_urls(self, page=1, site=None, protocol=None):
        # Use the configured production domain rather than
        # Django's default example.com domain.
        from django.contrib.sites.models import Site

        configured_domain = getattr(settings, "SITE_DOMAIN", "").strip()

        if configured_domain:
            site = Site(
                id=getattr(settings, "SITE_ID", 1),
                domain=configured_domain,
                name="FoodiePlug",
            )

        return super().get_urls(
            page=page,
            site=site,
            protocol=protocol or self.protocol,
        )