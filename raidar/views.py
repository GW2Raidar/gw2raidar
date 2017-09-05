from .models import *
from analyser.analyser import Analyser, Group, Archetype, EvtcAnalysisException
from analyser.bosses import BOSSES
from django.conf import settings
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm, PasswordResetForm
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.core import serializers
from django.core.mail import EmailMessage
from smtplib import SMTPException
from django.db.utils import IntegrityError
from django.http import JsonResponse, HttpResponse, Http404
from django.middleware.csrf import get_token
from django.shortcuts import render
from django.utils import timezone
from django.utils.http import urlsafe_base64_decode
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters, sensitive_variables
from django.views.decorators.http import require_GET, require_POST
from gw2api.gw2api import GW2API, GW2APIException
from itertools import groupby
from json import dumps as json_dumps, loads as json_loads
from os import makedirs, sep as dirsep
from os.path import join as path_join, isfile, dirname
import pytz
from datetime import datetime
from re import match, sub
from time import time
import logging


logger = logging.getLogger(__name__)


def _safe_get(f, default=None):
    try:
        return f()
    except (KeyError, TypeError):
        return default

def _error(msg, **kwargs):
    kwargs['error'] = str(msg)
    return JsonResponse(kwargs)


def _userprops(request):
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


def _encounter_data(request):
    participations = Participation.objects.filter(character__account__user=request.user).select_related('encounter', 'character', 'character__account')
    return [participation.data() for participation in participations]

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
    try:
        response['ga_property_id'] = settings.GA_PROPERTY_ID
    except:
        # No Google Analytics, it's fine
        pass
    response['archetypes'] = {k: v for k, v in Participation.ARCHETYPE_CHOICES}
    response['areas'] = {area.id: area.name for area in Area.objects.all()}
    response['specialisations'] = {p: {e: n for (pp, e), n in Character.SPECIALISATIONS.items() if pp == p} for p, _ in Character.PROFESSION_CHOICES}
    response['page'] = page
    response['debug'] = settings.DEBUG
    response['version'] = settings.VERSION
    if request.user.is_authenticated:
        try:
            last_notification = request.user.notifications.latest('id')
            response['last_notification_id'] = last_notification.id
        except Notification.DoesNotExist:
            # it's okay
            pass
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
def profile(request):
    if not request.user.is_authenticated:
        return _error("Not authenticated")

    user = request.user
    queryset = EraUserStore.objects.filter(user=user).select_related('era')
    try:
        eras = [{
                'name': era_user_store.era.name,
                'started_at': era_user_store.era.started_at,
                'description': era_user_store.era.description,
                'profile': era_user_store.val,
            } for era_user_store in queryset]
    except EraUserStore.DoesNotExist:
        eras = []

    profile = {
        'username': user.username,
        'joined_at': (user.date_joined - datetime.utcfromtimestamp(0).replace(tzinfo=pytz.UTC)).total_seconds(),
        'eras': eras,
    }

    result = {
            "profile": profile
        }
    return JsonResponse(result)



@require_GET
def encounter(request, url_id=None, json=None):
    try:
        encounter = Encounter.objects.select_related('area').get(url_id=url_id)
    except Encounter.DoesNotExist:
        if json:
            return _error("Encounter does not exist")
        else:
            raise Http404("Encounter does not exist")
    own_account_names = [account.name for account in Account.objects.filter(
        characters__participations__encounter_id=encounter.id,
        user=request.user)] if request.user.is_authenticated else []

    dump = json_loads(encounter.dump)
    members = [{ "name": name, **value } for name, value in dump['Category']['status']['Player'].items() if 'account' in value]

    try:
        area_stats = EraAreaStore.objects.get(era=encounter.era, area=encounter.area).val
    except EraAreaStore.DoesNotExist:
        area_stats = None
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
                            "mechanics": _safe_get(lambda: dump['Category']['combat']['Phase'][phase]['Subgroup'][str(party)]['Metrics']['mechanics']),
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
                    'mechanics': _safe_get(lambda: dump['Category']['combat']['Phase'][phase]['Player'][member['name']]['Metrics']['mechanics']),
                    'archetype': _safe_get(lambda: area_stats[phase]['build'][str(member['profession'])][str(member['elite'])][str(member['archetype'])]),
                } for phase in phases
            }

    data = {
        "encounter": {
            "evtc_version": _safe_get(lambda: dump['Category']['encounter']['evtc_version']),
            "id": encounter.id,
            "name": encounter.area.name,
            "filename": encounter.filename,
            "uploaded_at": encounter.uploaded_at,
            "uploaded_by": encounter.uploaded_by.username,
            "started_at": encounter.started_at,
            "duration": encounter.duration,
            "success": encounter.success,
            "phase_order": phases,
            "boss_metrics": [metric.__dict__ for metric in BOSSES[encounter.area_id].metrics],
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
                    'mechanics': _safe_get(lambda: dump['Category']['combat']['Phase'][phase]['Subgroup']['*All']['Metrics']['mechanics']),
                } for phase in phases
            },
            "parties": parties,
        }
    }
    if encounter.gdrive_url:
        data['encounter']['evtc_url'] = encounter.gdrive_url;
    # XXX relic TODO remove once we fully cross to GDrive?
    if hasattr(settings, 'UPLOAD_DIR'):
        path = path_join(settings.UPLOAD_DIR, encounter.uploaded_by.username.replace(dirsep, '_'), encounter.filename)
        if isfile(path):
            data['encounter']['downloadable'] = True

    if json:
        return JsonResponse(data)
    else:
        return _html_response(request, { "name": "encounter", "no": encounter.url_id }, data)


@require_GET
def initial(request):
    response = _userprops(request)
    if request.user.is_authenticated:
        response['encounters'] = _encounter_data(request)
    return JsonResponse(response)


@require_POST
@sensitive_post_parameters('password')
@sensitive_variables('password')
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


@sensitive_post_parameters('password')
@sensitive_variables('password')
def register(request):
    if request.method == 'GET':
        return index(request, page={ 'name': 'register' })

    username = request.POST.get('username').strip()
    password = request.POST.get('password').strip()
    email = request.POST.get('email').strip()
    api_key = request.POST.get('api_key').strip()
    gw2api = GW2API(api_key)

    try:
        token_info = gw2api.query("/tokeninfo")
        if 'gw2raidar' not in token_info['name'].lower():
            return _error("Your api key must be named 'gw2raidar'.")
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

    upload, _ = Upload.objects.update_or_create(
            filename=filename, uploaded_by=request.user,
            defaults={ "uploaded_at": time() })

    diskname = upload.diskname()
    makedirs(dirname(diskname), exist_ok=True)
    with open(diskname, 'wb') as diskfile:
        while True:
            buf = file.read(16384)
            if len(buf) == 0:
                break
            diskfile.write(buf)

    return JsonResponse({"filename": filename, "upload_id": upload.id})


@require_GET
def named(request, name, no):
    return index(request, { 'name': name, 'no': int(no) if type(no) == str else no })

@login_required
@require_POST
def poll(request):
    notifications = Notification.objects.filter(user=request.user)
    last_id = request.POST.get('last_id')
    if last_id:
        notifications = notifications.filter(id__gt=last_id)
    result = { "notifications": [notification.val for notification in notifications] }
    if notifications:
        result['last_id'] = notifications.last().id
    return JsonResponse(result)

@login_required
@require_POST
def change_email(request):
    request.user.email = request.POST.get('email')
    request.user.save()
    return JsonResponse({})

@login_required
@sensitive_post_parameters()
@sensitive_variables('form')
@require_POST
def change_password(request):
    form = PasswordChangeForm(request.user, request.POST)
    if form.is_valid():
        user = form.save()
        update_session_auth_hash(request, user)
        return JsonResponse({})
    else:
        return _error(' '.join(' '.join(v) for k, v in form.errors.items()))

@require_POST
def contact(request):
    subject = request.POST.get('subject')
    body = request.POST.get('body')
    if request.user.is_authenticated:
        name = request.user.username
        email = request.user.email
    else:
        name = request.POST.get('name')
        email = request.POST.get('email')

    try:
        headers = {'Reply-To': "%s <%s>" % (name, email)}
        msg = EmailMessage(
                settings.EMAIL_SUBJECT_PREFIX + '[contact] ' + subject,
                body,
                '"%s" <%s>' % (name, settings.DEFAULT_FROM_EMAIL),
                [settings.DEFAULT_FROM_EMAIL],
                reply_to=['%s <%s>' % (name, email)])
        msg.send(False)
    except SMTPException as e:
        return _error(e)

    return JsonResponse({})


@login_required
@require_POST
def add_api_key(request):
    api_key = request.POST.get('api_key').strip()
    gw2api = GW2API(api_key)
    
    try:
        token_info = gw2api.query("/tokeninfo")
        if 'gw2raidar' not in token_info['name'].lower():
            return _error("Your api key must be named 'gw2raidar'.")
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

    account.user = request.user
    account.api_key = api_key
    account.save()

    return JsonResponse({
        'account_name': account_name,
        'encounters': _encounter_data(request)
    })
