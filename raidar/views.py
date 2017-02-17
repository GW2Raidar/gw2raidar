from django.http import JsonResponse
from django.shortcuts import render
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.middleware.csrf import get_token
from django.contrib.auth.models import User
from django.db.utils import IntegrityError




def _error(msg, **kwargs):
    kwargs['error'] = msg
    return JsonResponse(kwargs)


def _login_successful(request, user):
    auth_login(request, user)
    csrftoken = get_token(request)
    return JsonResponse({
            'csrftoken': csrftoken,
            'username': user.username,
        })




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
        return _login_successful(request, user)
    else:
        return _error('Could not log in')


def register(request):
    username = request.POST.get('username')
    password = request.POST.get('password')
    email = request.POST.get('email')

    try:
        user = User.objects.create_user(username, email, password)
    except IntegrityError:
        return _error('Such a user already exists')

    if user:
        return _login_successful(request, user)
    else:
        return _error('Could not register user')


def logout(request):
    auth_logout(request)
    csrftoken = get_token(request)
    print(csrftoken)
    return HttpResponse()
