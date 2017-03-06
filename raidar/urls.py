from django.conf.urls import url
from django.contrib.auth import views as auth_views

from . import views

urlpatterns = [
        url(r'initial', views.initial, name = "initial"),
        url(r'login', views.login, name = "login"),
        url(r'logout', views.logout, name = "logout"),
        url(r'register', views.register, name = "register"),
        url(r'reset_pw', views.reset_pw, name = "reset_pw"),
        url(r'upload', views.upload, name = "upload"),
        url(r'^reset/(?P<uidb64>[0-9A-Za-z_\-]+)/(?P<token>[0-9A-Za-z]{1,13}-[0-9A-Za-z]{1,20})/$',
            auth_views.password_reset_confirm, name='password_reset_confirm'),
        url(r'^reset/done/$', auth_views.password_reset_complete, name='password_reset_complete'),
        url(r'^$', views.index, name = "index"),
]
