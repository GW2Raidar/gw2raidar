from json import dumps as json_dumps
from django.http import JsonResponse
from django.shortcuts import render
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.middleware.csrf import get_token
from django.contrib.auth.models import User
from django.db.utils import IntegrityError
from django.views.decorators.http import require_GET, require_POST
from django.contrib.auth.decorators import login_required
from evtcparser import *
from analyser import *




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



@require_GET
def index(request):
    username = None
    if request.user:
        username = request.user.username
    return render(request, template_name='raidar/index.html', context={
            'usernamejson': json_dumps(username)
        })


@require_GET
def user(request):
    username = None
    if request.user:
        username = request.user.username
    return JsonResponse({
            'username': request.user.username
        })


@require_POST
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


@require_POST
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


@login_required
@require_POST
def logout(request):
    auth_logout(request)
    csrftoken = get_token(request)
    return JsonResponse({})


@login_required
@require_POST
def upload(request):
    for filename, file in request.FILES.items():
        # TODO
        # file.name, file.content_type, file.size, file.read()
        e = parser.Encounter(file)

        # metrics is a tree with 2 types of nodes:
        # iterables containing key/value tuples
        # or basic values
        # should be easy to convert to json
        metrics = analyser.ComputeAllMetrics(e)

    return JsonResponse({})
