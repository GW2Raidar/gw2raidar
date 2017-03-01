from json import dumps as json_dumps
from django.http import JsonResponse
from django.shortcuts import render
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.middleware.csrf import get_token
from django.contrib.auth.models import User
from django.db.utils import IntegrityError
from django.views.decorators.http import require_GET, require_POST
from django.contrib.auth.decorators import login_required
from evtcparser.parser import Encounter as EvtcEncounter
from analyser.analyser import Analyser
from datetime import datetime
from django.utils import timezone
from django.core import serializers
from re import match
from .models import *




def _error(msg, **kwargs):
    kwargs['error'] = msg
    return JsonResponse(kwargs)


def _userprops(request):
    if request.user:
        return {
                'username': request.user.username,
                'is_staff': request.user.is_staff
            }
    else:
        return {}

def _encounter_data(request):
    encounters = Encounter.objects.filter(characters__account__user=request.user)
    return [{
            'id': encounter.id,
            'area': encounter.area.name,
            'started_at': int(encounter.started_at.strftime('%s')),
        } for encounter in encounters]

def _login_successful(request, user):
    auth_login(request, user)
    csrftoken = get_token(request)
    userprops = _userprops(request)
    userprops['csrftoken'] = csrftoken
    userprops['encounters'] = _encounter_data(request)
    return JsonResponse(userprops)



@require_GET
def index(request):
    return render(request, template_name='raidar/index.html', context={
            'userprops': json_dumps(_userprops(request))
        })


@require_GET
def initial(request):
    response = _userprops(request)
    if request.user.is_authenticated():
        response['encounters'] = _encounter_data(request)
    return JsonResponse(response)


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
    user_account_names = [account.name for account in request.user.accounts.all()]

    result = {}
    # TODO this should really only be one file
    # so make adjustments to find out its name and only provide one result

    for filename, file in request.FILES.items():
        evtc_encounter = EvtcEncounter(file)
        area = Area.objects.get(id=evtc_encounter.area_id)
        if not area:
            return _error('Unknown area')

        analyser = Analyser(evtc_encounter)
        players = analyser.players
        if players.empty:
            return _error('No players in encounter')

        started_at = datetime.fromtimestamp(analyser.info['start'])
        # TODO take timezone from Profile
        started_at = timezone.make_aware(started_at, timezone.utc)

        # heuristics to see if the encounter is a re-upload:
        # a character can only be in one raid at a time
        # XXX: it is *theoretically* possible for this to be in a race
        # condition, so that the encounter is duplicated and later raises an
        # error. try/catch, if returns multiple then delete all but one?
        encounter, encounter_created = Encounter.objects.get_or_create(
                area=area, started_at=started_at, characters__name=players['name'].iloc[0])

        show = False
        for player in players.itertuples():
            if player.account in user_account_names:
                show = True
            account, _ = Account.objects.get_or_create(
                    name=player.account)
            character, _ = Character.objects.get_or_create(
                    name=player.name, account=account, profession=player.prof)
            participation, _ = Participation.objects.get_or_create(
                    character=character, encounter=encounter, archetype=player.archetype,
                    party=player.party)
        if show:
            result[filename] = {
                    'id': encounter.id,
                    'area': encounter.area.name,
                    'started_at': started_at,
                    'new': encounter_created,
                }

    return JsonResponse(result)
