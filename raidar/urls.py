from django.conf.urls import url

from . import views

urlpatterns = [
        url(r'initial', views.initial, name = "initial"),
        url(r'^(?P<name>encounters|profile|account|register|login|index)(?:/(?P<no>\d+))?$', views.named, name = "named"),
        url(r'login.json', views.login, name = "login"),
        url(r'logout.json', views.logout, name = "logout"),
        url(r'register.json', views.register, name = "register"),
        url(r'upload.json', views.upload, name = "upload"),
        url(r'change_email.json', views.change_email, name = "change_email"),
        url(r'change_password.json', views.change_password, name = "change_password"),
        url(r'add_api_key', views.add_api_key, name = "add_api_key"),
        url(r'^encounter/(?P<id>\d+)(?P<json>\.json)?$', views.encounter, name = "encounter"),
        url(r'^$', views.index, name = "index"),
]
