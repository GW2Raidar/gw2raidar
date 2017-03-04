from json import dumps as json_dumps
from django.http import JsonResponse
from django.shortcuts import render
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.middleware.csrf import get_token
from django.contrib.auth.models import User
from django.db.utils import IntegrityError
from django.views.decorators.http import require_GET, require_POST
from django.contrib.auth.decorators import login_required
from evtcparser.parser import Encounter as EvtcEncounter, EvtcParseException
from analyser.analyser import Analyser
from django.utils import timezone
from django.db import transaction
from django.core import serializers
from re import match
from .models import *
from gw2api.gw2api import GW2API, GW2APIException






def _error(msg, **kwargs):
    kwargs['error'] = str(msg)
    return JsonResponse(kwargs)


def _userprops(request):
    if request.user:
        return {
                'username': request.user.username,
                'is_staff': request.user.is_staff
            }
    else:
        return {}

def _participation_data(participation):
    return {
            'id': participation.encounter.id,
            'area': participation.encounter.area.name,
            'started_at': participation.encounter.started_at,
            'character': participation.character.name,
            'account': participation.character.account.name,
            'profession': participation.character.profession,
            'archetype': participation.archetype,
        }


def _encounter_data(request):
    participations = Participation.objects.filter(character__account__user=request.user).select_related('encounter', 'character', 'character__account')
    return [_participation_data(participation) for participation in participations]

def _login_successful(request, user):
    auth_login(request, user)
    csrftoken = get_token(request)
    userprops = _userprops(request)
    userprops['csrftoken'] = csrftoken
    userprops['encounters'] = _encounter_data(request)
    return JsonResponse(userprops)





@require_GET
def index(request):
    response = _userprops(request)
    response['archetypes'] = {k: v for k, v in Participation.ARCHETYPE_CHOICES}
    response['professions'] = {k: v for k, v in Character.PROFESSION_CHOICES}
    return render(request, template_name='raidar/index.html', context={
            'userprops': json_dumps(response),
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
    api_key = request.POST.get('api_key')
    gw2api = GW2API(api_key)

    try:
        gw2_account = gw2api.query("/account")
    except GW2APIException as e:
        return _error(e)

    try:
        with transaction.atomic():
            try:
                user = User.objects.create_user(username, email, password)
            except IntegrityError:
                return _error('Such a user already exists')

            if not user:
                return _error('Could not register user')

            account_name = gw2_account['name']
            account = Account.objects.get_or_create(user=user, api_key=api_key, name=account_name)

            return _login_successful(request, user)

    except IntegrityError:
        return _error('The user with that GW2 account is already registered')


@login_required
@require_POST
def logout(request):
    auth_logout(request)
    csrftoken = get_token(request)
    return JsonResponse({})


@login_required
@require_POST
def upload(request):
    result = {}
    # TODO this should really only be one file
    # so make adjustments to find out its name and only provide one result

    for filename, file in request.FILES.items():
        try:
            evtc_encounter = EvtcEncounter(file)
        except EvtcParseException as e:
            return _error(e)

        area = Area.objects.get(id=evtc_encounter.area_id)
        if not area:
            return _error('Unknown area')

        analyser = Analyser(evtc_encounter)
        players = analyser.players
        if players.empty:
            return _error('No players in encounter')

        if analyser.info['end'] - analyser.info['start'] < 60:
            return _error('Encounter shorter than 60s')

        started_at = analyser.info['start']

        # heuristics to see if the encounter is a re-upload:
        # a character can only be in one raid at a time
        # account_names are being hashed, and the triplet
        # (area, account_hash, started_at) is being checked for
        # uniqueness (along with some fuzzing to started_at)
        account_names = list(players['account'])
        encounter, encounter_created = Encounter.objects.get_or_create(
                area=area, started_at=started_at,
                account_names=account_names,
                dump=json_dumps(analyser.data))

        for player in players.itertuples():
            account, _ = Account.objects.get_or_create(
                    name=player.account)
            character, _ = Character.objects.get_or_create(
                    name=player.name, account=account, profession=player.prof)
            participation, _ = Participation.objects.get_or_create(
                    character=character, encounter=encounter,
                    archetype=player.archetype, party=player.party)

        own_participation = encounter.participations.filter(character__account__user=request.user).first()
        if own_participation:
            result[filename] = _participation_data(own_participation)

    return JsonResponse(result)
