from .models import *
from analyser.analyser import Analyser, Group, Archetype, EvtcAnalysisException
from django.conf import settings
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm, PasswordResetForm
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.core import serializers
from django.db import transaction
from django.db.utils import IntegrityError
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import render
from django.utils import timezone
from django.utils.http import urlsafe_base64_decode
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_GET, require_POST
from evtcparser.parser import Encounter as EvtcEncounter, EvtcParseException
from gw2api.gw2api import GW2API, GW2APIException
from itertools import groupby
from json import dumps as json_dumps, loads as json_loads
from re import match
from time import time
from zipfile import ZipFile




def _safe_get(f):
    try:
        return f()
    except KeyError:
        return None

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
            'duration': participation.encounter.duration,
            'character': participation.character.name,
            'account': participation.character.account.name,
            'profession': participation.character.profession,
            'archetype': participation.archetype,
            'elite': participation.elite,
            'uploaded_at': participation.encounter.uploaded_at,
            'success': participation.encounter.success,
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




def _html_response(request, page, data={}):
    response = _userprops(request)
    response.update(data)
    response['ga_property_id'] = settings.GA_PROPERTY_ID
    response['archetypes'] = {k: v for k, v in Participation.ARCHETYPE_CHOICES}
    response['specialisations'] = {p: {e: n for (pp, e), n in Character.SPECIALISATIONS.items() if pp == p} for p, _ in Character.PROFESSION_CHOICES}
    response['page'] = page
    return render(request, template_name='raidar/index.html', context={
            'userprops': json_dumps(response),
        })

@require_GET
def index(request, page={ 'name': 'encounters', 'no': 1 }):
    return _html_response(request, page)

@require_GET
def encounter(request, id=None, json=None):
    encounter = Encounter.objects.select_related('area').get(pk=id)
    own_account_names = [account.name for account in Account.objects.filter(
        characters__participations__encounter_id=encounter.id,
        user=request.user)]
    dump = json_loads(encounter.dump)
    area_stats = json_loads(encounter.area.stats)
    phases = dump['Category']['combat']['Phase'].keys()
    members = [{ "name": name, **value } for name, value in dump['Category']['status']['Player'].items() if 'account' in value]
    keyfunc = lambda member: member['party']
    parties = { party: {
                    "members": list(members),
                    "phases": {
                        phase: {
                            "actual": dump['Category']['combat']['Phase'][phase]['Subgroup'][str(party)]['Metrics']['damage']['To']['*All'],
                            "actual_boss": dump['Category']['combat']['Phase'][phase]['Subgroup'][str(party)]['Metrics']['damage']['To']['*Boss'],
                            "received": dump['Category']['combat']['Phase'][phase]['Subgroup'][str(party)]['Metrics']['damage']['From']['*All'],
                            "buffs": dump['Category']['combat']['Phase'][phase]['Subgroup'][str(party)]['Metrics']['buffs']['From']['*All'],
                        } for phase in phases
                    }
                } for party, members in groupby(sorted(members, key=keyfunc), keyfunc) }
    for party_no, party in parties.items():
        for member in party['members']:
            if member['account'] in own_account_names:
                member['self'] = True
            member['phases'] = {
                phase: {
                    'actual': _safe_get(lambda: dump['Category']['combat']['Phase'][phase]['Player'][member['name']]['Metrics']['damage']['To']['*All']),
                    'actual_boss': _safe_get(lambda: dump['Category']['combat']['Phase'][phase]['Player'][member['name']]['Metrics']['damage']['To']['*Boss']),
                    'buffs': _safe_get(lambda: dump['Category']['combat']['Phase'][phase]['Player'][member['name']]['Metrics']['buffs']['From']['*All']),
                    'received': _safe_get(lambda: dump['Category']['combat']['Phase'][phase]['Player'][member['name']]['Metrics']['damage']['From']['*All']),
                    'archetype': _safe_get(lambda: area_stats[phase]['build'][str(member['profession'])][str(member['elite'])][str(member['archetype'])]),
                } for phase in phases
            }
    data = {
        "encounter": {
            "name": encounter.area.name,
            "started_at": encounter.started_at,
            "duration": encounter.duration,
            "success": encounter.success,
            "phases": {
                phase: {
                    'group': _safe_get(lambda: area_stats[phase]['group']),
                    'individual': _safe_get(lambda: area_stats[phase]['individual']),
                    'actual': _safe_get(lambda: dump['Category']['combat']['Phase'][phase]['Subgroup']['*All']['Metrics']['damage']['To']['*All']),
                    'actual_boss': _safe_get(lambda: dump['Category']['combat']['Phase'][phase]['Subgroup']['*All']['Metrics']['damage']['To']['*Boss']),
                    'received': _safe_get(lambda: dump['Category']['combat']['Phase'][phase]['Subgroup']['*All']['Metrics']['damage']['From']['*All']),
                    'buffs': _safe_get(lambda: dump['Category']['combat']['Phase'][phase]['Subgroup']['*All']['Metrics']['buffs']['From']['*All']),
                } for phase in phases
            },
            "parties": parties,
        }
    }

    if json:
        return JsonResponse(data)
    else:
        return _html_response(request, { "name": "encounter", "no": str(id) }, data)


@require_GET
def initial(request):
    response = _userprops(request)
    if request.user.is_authenticated():
        response['encounters'] = _encounter_data(request)
    return JsonResponse(response)


def login(request):
    if request.method == 'GET':
        return index(request, page={ 'name': 'login' })

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
@sensitive_post_parameters()
@never_cache
def reset_pw(request):
    email = request.POST.get('email')
    form = PasswordResetForm(request.POST)
    if form.is_valid():
        opts = {
            'use_https': request.is_secure(),
            'email_template_name': 'registration/password_reset_email.html',
            'subject_template_name': 'registration/password_reset_subject.txt',
            'request': request,
        }
        form.save(**opts)
        return JsonResponse({});



def register(request):
    if request.method == 'GET':
        return index(request, page={ 'name': 'register' })

    username = request.POST.get('username')
    password = request.POST.get('password')
    email = request.POST.get('email')
    api_key = request.POST.get('api_key')
    gw2api = GW2API(api_key)

    try:
        gw2_account = gw2api.query("/account")
    except GW2APIException as e:
        return _error(e)

    account_name = gw2_account['name']
    account, _ = Account.objects.get_or_create(name=account_name)

    if account.user and account.user != request.user:
        # Registered to another account
        old_gw2api = GW2API(account.api_key)
        try:
            gw2_account = old_gw2api.query("/account")
            # Old key is still valid, ask user to invalidate it
            try:
                old_api_key_info = old_gw2api.query("/tokeninfo")
                key_id = "named '%s'" % old_api_key_info['name']
            except GW2APIException as e:
                key_id = "ending in '%s'" % api_key[-4:]
            new_key = "" if account.api_key != api_key else " and generate a new key"

            return _error("This GW2 account is registered to another user. To prove it is yours, please invalidate the key %s%s." % (key_id, new_key))
        except GW2APIException as e:
            # Old key is invalid, reassign OK
            pass

    try:
        user = User.objects.create_user(username, email, password)
    except IntegrityError:
        return _error('Such a user already exists')

    if not user:
        return _error('Could not register user')

    account.user = user
    account.api_key = api_key
    account.save()

    return _login_successful(request, user)


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
        zipfile = None
        if filename.endswith('.evtc.zip'):
            zipfile = ZipFile(file)
            contents = zipfile.infolist()
            if len(contents) == 1:
                file = zipfile.open(contents[0].filename)
            else:
                return _error('Only single-file ZIP archives are allowed')

        try:
            evtc_encounter = EvtcEncounter(file)
        except EvtcParseException as e:
            return _error(e)

        if zipfile:
            zipfile.close()

        area = Area.objects.get(id=evtc_encounter.area_id)
        if not area:
            return _error('Unknown area')

        try:
            analyser = Analyser(evtc_encounter)
        except EvtcAnalysisException as e:
            return _error(e)

        dump = analyser.data

        # XXX

        started_at = dump['Category']['encounter']['start']
        duration = dump['Category']['encounter']['duration']
        success = dump['Category']['encounter']['success']

        if duration < 60:
            return _error('Encounter shorter than 60s')

        # heuristics to see if the encounter is a re-upload:
        # a character can only be in one raid at a time
        # account_names are being hashed, and the triplet
        # (area, account_hash, started_at) is being checked for
        # uniqueness (along with some fuzzing to started_at)
        status_for = {name: player for name, player in dump[Group.CATEGORY]['status']['Player'].items() if 'account' in player}
        account_names = [player['account'] for player in status_for.values()]
        try:
            with transaction.atomic():
                encounter, _ = Encounter.objects.update_or_create(
                    area=area, started_at=started_at, account_names=account_names,
                    defaults = {
                        'filename': filename,
                        'uploaded_at': time(),
                        'uploaded_by': request.user,
                        'duration': duration,
                        'success': success,
                        'dump': json_dumps(dump),
                    }
                )

                for name, player in status_for.items():
                    account, _ = Account.objects.get_or_create(
                        name=player['account'])
                    character, _ = Character.objects.get_or_create(
                        name=name, account=account, profession=player['profession'])
                    participation, _ = Participation.objects.update_or_create(
                        character=character, encounter=encounter,
                        defaults = {
                            'archetype': player['archetype'],
                            'party': player['party'],
                            'elite': player['elite']
                        }
                    )
        except IntegrityError as e:
            # DEBUG
            logger = logging.getLogger(__name__)
            logger.error(e)
            print(e, file=sys.stderr)
            return _error("Conflict with an uploaded encounter")

        own_participation = encounter.participations.filter(character__account__user=request.user).first()
        if own_participation:
            result[filename] = _participation_data(own_participation)

    return JsonResponse(result)


@require_GET
def named(request, name, no):
    return index(request, { 'name': name, 'no': no })

@login_required
@require_POST
def change_email(request):
    request.user.email = request.POST.get('email')
    request.user.save()
    return JsonResponse({})

@login_required
@require_POST
def change_password(request):
    form = PasswordChangeForm(request.user, request.POST)
    if form.is_valid():
        user = form.save()
        update_session_auth_hash(request, user)
        return JsonResponse({})
    else:
        return _error(' '.join(' '.join(v) for k, v in form.errors.items()))

@login_required
@require_POST
def add_api_key(request):
    api_key = request.POST.get('api_key')
    gw2api = GW2API(api_key)

    try:
        gw2_account = gw2api.query("/account")
    except GW2APIException as e:
        return _error(e)

    account_name = gw2_account['name']
    account, _ = Account.objects.get_or_create(name=account_name)

    if account.user and account.user != request.user:
        # Registered to another account
        old_gw2api = GW2API(account.api_key)
        try:
            gw2_account = old_gw2api.query("/account")
            # Old key is still valid, ask user to invalidate it
            try:
                old_api_key_info = old_gw2api.query("/tokeninfo")
                key_id = "named '%s'" % old_api_key_info['name']
            except GW2APIException as e:
                key_id = "ending in '%s'" % api_key[-4:]
            new_key = "" if account.api_key != api_key else " and generate a new key"

            return _error("This account is registered to another user. To confirm this account is yours, please invalidate the key %s%s." % (key_id, new_key))
        except GW2APIException as e:
            # Old key is invalid, reassign OK
            pass

    account.user = request.user
    account.api_key = api_key
    account.save()

    return JsonResponse({
        'account_name': account_name,
        'encounters': _encounter_data(request)
    })
