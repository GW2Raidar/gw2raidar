from django.conf import settings
from django.conf.urls import url, include
from django.contrib.auth import views as auth_views
from django.views.generic.base import TemplateView
import importlib
from rest_framework.authtoken import views as rest_auth_views, serializers as rest_auth_serializers
from rest_framework_swagger.views import get_swagger_view

from . import views
from .api_v2 import views as api_v2_views

urlpatterns = [
    url(r'^(?P<name>encounters|profile|uploads|account|register|login|index|reset_pw|thank-you|info-(?:help|releasenotes|contact|about|framework))(?:/(?P<no>\w+))?$', views.named, name = "named"),
    url(r'^initial.json$', views.initial, name = "initial"),
    url(r'^login.json$', views.login, name = "login"),
    url(r'^logout.json$', views.logout, name = "logout"),
    url(r'^register.json$', views.register, name = "register"),
    url(r'^reset_pw.json$', views.reset_pw, name = "reset_pw"),
    url(r'^upload.json$', views.upload, name = "upload"),
    url(r'^api/upload.json$', views.api_upload, name = "api_upload"),
    url(r'^api/categories.json$', views.api_categories, name = "api_categories"),
    url(r'^privacy.json$', views.privacy, name = "privacy"),
    url(r'^profile_graph.json$', views.profile_graph, name = "profile_graph"),
    url(r'^set_tags_cat.json$', views.set_tags_cat, name = "set_tags_cat"),
    url(r'^contact.json$', views.contact, name = "contact"),
    url(r'^poll.json$', views.poll, name = "poll"),
    url(r'^change_email.json$', views.change_email, name = "change_email"),
    url(r'^change_password.json$', views.change_password, name = "change_password"),
    url(r'^add_api_key.json$', views.add_api_key, name = "add_api_key"),
    url(r'^encounter/(?P<url_id>\w+)(?P<json>\.json)?$', views.encounter, name = "encounter"),
    url(r'^profile.json$', views.profile, name = "profile"),
    url(r'^reset/(?P<uidb64>[0-9A-Za-z_\-]+)/(?P<token>[0-9A-Za-z]{1,13}-[0-9A-Za-z]{1,20})/$',
        auth_views.password_reset_confirm, name='password_reset_confirm'),
    url(r'^reset/done/$', auth_views.password_reset_complete, name='password_reset_complete'),
    url(r'^download/(?P<url_id>\w+)?$', views.download, name="download"),
    url(r'^$', views.index, name = "index"),
    url(r'^robots.txt$', TemplateView.as_view(template_name='raidar/robots.txt'), name="robots"),
    # XXX HACK separate API
    url(r'^(?:api/)?global_stats(?:/(?P<era_id>[0-9]+))?(?:/area-(?P<area_id>[0-9]+))?(?P<json>\.json)?$', views.global_stats, name = "global_stats"),
]

class ObtainAuthToken(rest_auth_views.ObtainAuthToken):
    def get_serializer(self):
        return rest_auth_serializers.AuthTokenSerializer()



urlpatterns += [
    url(r'^api/v2/auth/', include('rest_framework.urls', namespace='rest_framework')),
    url(r'^api/v2/token', ObtainAuthToken.as_view()),
    url(r'^api/v2/swagger', get_swagger_view(title='GW2Raidar API')),
    url(r'^api/v2/categories', api_v2_views.CategoryListView.as_view()),
    url(r'^api/v2/areas', api_v2_views.AreaListView.as_view()),
    url(r'^api/v2/encounters/new', api_v2_views.EncounterUploadView.as_view()),
    url(r'^api/v2/encounters', api_v2_views.EncounterListView.as_view()),
]


if settings.DEBUG and importlib.util.find_spec('debug_toolbar'):
    import debug_toolbar
    urlpatterns = [
        url(r'^__debug__/', include(debug_toolbar.urls)),
    ] + urlpatterns
