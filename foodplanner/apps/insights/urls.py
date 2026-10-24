from django.urls import path

from . import views


app_name = "insights"


urlpatterns = [
    # /insights/  ->  {% url 'insights:overview' %}
    path("", views.insights_page, name="overview"),
]

# ---------------------------------------------------------------------
# Wire it into the project (config/urls.py), next to your other apps:
#
#     path("insights/", include("apps.insights.urls")),
#
# and make sure "apps.insights" is in INSTALLED_APPS (this app has no models,
# so there is nothing to migrate).
#
# Then point the sidebar's "Insights" link (currently href="#") at it:
#
#     <a href="{% url 'insights:overview' %}" class="nav-item">
# ---------------------------------------------------------------------