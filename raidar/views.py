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
from django.http import JsonResponse, HttpResponse, Http404
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
from os import makedirs, sep as dirsep
from os.path import join as path_join, isfile
from re import match, sub
from time import time
from zipfile import ZipFile
import logging


logger = logging.getLogger(__name__)


def _safe_get(f, default=None):
    try:
        return f()
    except KeyError:
        return default

def _error(msg, **kwargs):
    kwargs['error'] = str(msg)
    return JsonResponse(kwargs)


def _userprops(request):
    if request.user:
        accounts = request.user.accounts.all() if request.user.is_authenticated else []
        return {
                'username': request.user.username,
                'is_staff': request.user.is_staff,
                'accounts': [{
                        "name": account.name,
                        "api_key": account.api_key[:8] +
                                   sub(r"[0-9a-fA-F]", "X", account.api_key[8:-12]) +
                                   account.api_key[-12:]
                                   if account.api_key != "" else "",
                    }
                    for account in accounts],
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
def download(request, id=None):
    if not hasattr(settings, 'UPLOAD_DIR'):
        return Http404("Not allowed")

    encounter = Encounter.objects.get(pk=id)
    own_account_names = [account.name for account in Account.objects.filter(
        characters__participations__encounter_id=encounter.id,
        user=request.user)]
    dump = json_loads(encounter.dump)
    members = [{ "name": name, **value } for name, value in dump['Category']['status']['Player'].items() if 'account' in value]
    allowed = request.user.is_staff or any(member['account'] in own_account_names for member in members)
    if not allowed:
        raise Http404("Not allowed")

    path = path_join(settings.UPLOAD_DIR, encounter.uploaded_by.username.replace(dirsep, '_'), encounter.filename)
    if isfile(path):
        response = HttpResponse(open(path, 'rb'), content_type='application/vnd.ms-excel')
        response['Content-Disposition'] = 'attachment; filename="%s"' % encounter.filename
        return response
    else:
        raise Http404("Not allowed")

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
    members = [{ "name": name, **value } for name, value in dump['Category']['status']['Player'].items() if 'account' in value]
    allowed = request.user.is_staff or any(member['account'] in own_account_names for member in members)
    if not allowed:
        return _error('Not allowed')

    area_stats = json_loads(encounter.area.stats)
    phases = _safe_get(lambda: dump['Category']['encounter']['phase_order'] + ['All'], list(dump['Category']['combat']['Phase'].keys()))
    partyfunc = lambda member: member['party']
    namefunc = lambda member: member['name']
    parties = { party: {
                    "members": sorted(members, key=namefunc),
                    "phases": {
                        phase: {
                            "actual": _safe_get(lambda: dump['Category']['combat']['Phase'][phase]['Subgroup'][str(party)]['Metrics']['damage']['To']['*All']),
                            "actual_boss": _safe_get(lambda: dump['Category']['combat']['Phase'][phase]['Subgroup'][str(party)]['Metrics']['damage']['To']['*Boss']),
                            "received": _safe_get(lambda: dump['Category']['combat']['Phase'][phase]['Subgroup'][str(party)]['Metrics']['damage']['From']['*All']),
                            "buffs": _safe_get(lambda: dump['Category']['combat']['Phase'][phase]['Subgroup'][str(party)]['Metrics']['buffs']['From']['*All']),
                            "events": _safe_get(lambda: dump['Category']['combat']['Phase'][phase]['Subgroup'][str(party)]['Metrics']['events']),
                        } for phase in phases
                    }
                } for party, members in groupby(sorted(members, key=partyfunc), partyfunc) }
    for party_no, party in parties.items():
        for member in party['members']:
            if member['account'] in own_account_names:
                member['self'] = True
            member['phases'] = {
                phase: {
                    'actual': _safe_get(lambda: dump['Category']['combat']['Phase'][phase]['Player'][member['name']]['Metrics']['damage']['To']['*All']),
                    'actual_boss': _safe_get(lambda: dump['Category']['combat']['Phase'][phase]['Player'][member['name']]['Metrics']['damage']['To']['*Boss']),
                    'received': _safe_get(lambda: dump['Category']['combat']['Phase'][phase]['Player'][member['name']]['Metrics']['damage']['From']['*All']),
                    'buffs': _safe_get(lambda: dump['Category']['combat']['Phase'][phase]['Player'][member['name']]['Metrics']['buffs']['From']['*All']),
                    'events': _safe_get(lambda: dump['Category']['combat']['Phase'][phase]['Player'][member['name']]['Metrics']['events']),
                    'archetype': _safe_get(lambda: area_stats[phase]['build'][str(member['profession'])][str(member['elite'])][str(member['archetype'])]),
                } for phase in phases
            }

    data = {
        "encounter": {
            "evtc_version": _safe_get(lambda: dump['Category']['encounter']['evtc_version']),
            "name": encounter.area.name,
            "filename": encounter.filename,
            "uploaded_at": encounter.uploaded_at,
            "uploaded_by": encounter.uploaded_by.username,
            "started_at": encounter.started_at,
            "duration": encounter.duration,
            "success": encounter.success,
            "phase_order": phases,
            "phases": {
                phase: {
                    'duration': encounter.duration if phase == "All" else _safe_get(lambda: dump['Category']['encounter']['Phase'][phase]['duration']),
                    'group': _safe_get(lambda: area_stats[phase]['group']),
                    'individual': _safe_get(lambda: area_stats[phase]['individual']),
                    'actual': _safe_get(lambda: dump['Category']['combat']['Phase'][phase]['Subgroup']['*All']['Metrics']['damage']['To']['*All']),
                    'actual_boss': _safe_get(lambda: dump['Category']['combat']['Phase'][phase]['Subgroup']['*All']['Metrics']['damage']['To']['*Boss']),
                    'received': _safe_get(lambda: dump['Category']['combat']['Phase'][phase]['Subgroup']['*All']['Metrics']['damage']['From']['*All']),
                    'buffs': _safe_get(lambda: dump['Category']['combat']['Phase'][phase]['Subgroup']['*All']['Metrics']['buffs']['From']['*All']),
                    'events': _safe_get(lambda: dump['Category']['combat']['Phase'][phase]['Subgroup']['*All']['Metrics']['events']),
                } for phase in phases
            },
            "parties": parties,
        }
    }
    if hasattr(settings, 'UPLOAD_DIR'):
        path = path_join(settings.UPLOAD_DIR, encounter.uploaded_by.username.replace(dirsep, '_'), encounter.filename)
        if isfile(path):
            data['encounter']['downloadable'] = True

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

    username = request.POST.get('username').strip()
    password = request.POST.get('password').strip()
    email = request.POST.get('email').strip()
    api_key = request.POST.get('api_key').strip()
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
    if (len(request.FILES) != 1):
        return _error("Only single file uploads are allowed")

    filename = next(iter(request.FILES))
    file = request.FILES[filename]
    uploaded_at = time()

    if hasattr(settings, 'UPLOAD_DIR'):
        dir = path_join(settings.UPLOAD_DIR, request.user.username.replace(dirsep, '_'))
        makedirs(path_join(dir), exist_ok=True)
        diskname = path_join(dir, filename)
        with open(diskname, 'wb') as diskfile:
            while True:
                buf = file.read(16384)
                if len(buf) == 0:
                    break
                diskfile.write(buf)
        file = open(diskname, 'rb')

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
    file.close()

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

    status_for = {name: player for name, player in dump[Group.CATEGORY]['status']['Player'].items() if 'account' in player}
    account_names = [player['account'] for player in status_for.values()]
    with transaction.atomic():
        # heuristics to see if the encounter is a re-upload:
        # a character can only be in one raid at a time
        # account_names are being hashed, and the triplet
        # (area, account_hash, started_at) is being checked for
        # uniqueness (along with some fuzzing to started_at)
        started_at_full, started_at_half = Encounter.calculate_start_guards(started_at)
        account_hash = Encounter.calculate_account_hash(account_names)
        try:
            encounter = Encounter.objects.get(
                Q(started_at_full=started_at_full) | Q(started_at_half=started_at_half),
                area=area, account_hash=account_hash
            )
            encounter.filename = filename
            encounter.uploaded_at = uploaded_at
            encounter.uploaded_by = request.user
            encounter.duration = duration
            encounter.success = success
            encounter.dump = json_dumps(dump)
            encounter.started_at = started_at
            encounter.started_at_full = started_at_full
            encounter.started_at_half = started_at_half
            encounter.save()
        except Encounter.DoesNotExist:
            encounter = Encounter.objects.create(
                filename=filename, uploaded_at=time(), uploaded_by=request.user,
                duration=duration, success=success, dump=json_dumps(dump),
                area=area, started_at=started_at,
                started_at_full=started_at_full, started_at_half=started_at_half,
                account_hash=account_hash
            )

        for name, player in status_for.items():
            account, _ = Account.objects.get_or_create(
                name=player['account'])
            character, _ = Character.objects.get_or_create(
                name=name, account=account,
                defaults={
                    'profession': player['profession']
                }
            )
            participation, _ = Participation.objects.update_or_create(
                character=character, encounter=encounter,
                defaults={
                    'archetype': player['archetype'],
                    'party': player['party'],
                    'elite': player['elite']
                }
            )

    result = { 'id': encounter.id }
    own_participation = encounter.participations.filter(character__account__user=request.user).first()
    if own_participation:
        result['encounter'] = _participation_data(own_participation)

    return JsonResponse(result)


@require_GET
def named(request, name, no):
    return index(request, { 'name': name, 'no': int(no) if type(no) == str else no })

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
    api_key = request.POST.get('api_key').strip()
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
