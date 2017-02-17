from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import render
from django.contrib.auth import authenticate, login as auth_login


def index(request):
    return render(request, template_name='raidar/index.html')

def login(request):
    username = request.POST.get('username')
    password = request.POST.get('password')
    # stayloggedin = request.GET.get('stayloggedin')
    # if stayloggedin == "true":
    #     pass
    # else:
    #     request.session.set_expiry(0)

    user = authenticate(username=username, password=password)
    if user is not None and user.is_active:
        auth_login(request, user)
        return HttpResponse()
    else:
        return HttpResponseForbidden()
