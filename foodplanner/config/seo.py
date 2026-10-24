from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.http import require_GET


@require_GET
def robots_txt(request):
    lines = [
        "User-agent: *",
        "Allow: /",
        "Disallow: /admin/",
        "Disallow: /dashboard/",
        "Disallow: /profile/",
        "Disallow: /settings/",
        "Disallow: /ai/",
        "Disallow: /pantry/",
        "Disallow: /budgets/",
        "Disallow: /insights/",
    ]

    if not settings.DEBUG:
        site_url = getattr(settings, "SITE_URL", "").rstrip("/")
        if site_url:
            lines.extend([
                "",
                f"Sitemap: {site_url}/sitemap.xml",
            ])

    return HttpResponse(
        "\n".join(lines) + "\n",
        content_type="text/plain; charset=utf-8",
    )