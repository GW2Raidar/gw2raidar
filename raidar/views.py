from .models import *
from analyser.analyser import Analyser, Group, Profession, SPECIALISATIONS, Archetype, EvtcAnalysisException
from analyser.bosses import BOSSES, BOSS_LOCATIONS
from analyser.buffs import BUFF_TYPES, BUFF_TABS, StackType
from django.conf import settings
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm, PasswordResetForm
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.contrib.staticfiles.templatetags.staticfiles import static
from django.core import serializers
from django.core.mail import EmailMessage
from django.views.decorators.csrf import csrf_exempt
from smtplib import SMTPException
from django.db.utils import IntegrityError
from django.http import JsonResponse, HttpResponse, Http404, UnreadablePostError
from django.middleware.csrf import get_token
from django.shortcuts import render
from django.utils import timezone
from django.utils.http import urlsafe_base64_decode
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters, sensitive_variables
from django.views.decorators.http import require_GET, require_POST
from gw2api.gw2api import GW2API, GW2APIException
from itertools import groupby
from json import dumps as json_dumps
from os import makedirs, sep as dirsep
from os.path import join as path_join, isfile, dirname
import pytz
from datetime import datetime
from re import match, sub
from time import time
import logging
import numpy as np
import base64



logger = logging.getLogger(__name__)


def _safe_get(f, default=None):
    try:
        return f()
    except (KeyError, TypeError):
        return default

def _error(msg, status=200, **kwargs):
    kwargs['error'] = str(msg)
    return JsonResponse(kwargs, status=status)


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
                'encounter_count': Encounter.objects.count(),
            }


def _encounter_data(request):
    participations = Participation.objects.filter(account__user=request.user).select_related('encounter', 'account', 'encounter__area').prefetch_related('encounter__tagged_items__tag').iterator()
    return [participation.data() for participation in participations]

def _login_successful(request, user):
    auth_login(request, user)
    csrftoken = get_token(request)
    userprops = _userprops(request)
    userprops['csrftoken'] = csrftoken
    userprops['encounters'] = _encounter_data(request)
    userprops['privacy'] = request.user.user_profile.privacy
    return JsonResponse(userprops)



def _buff_data(buff):
    data = { "name": buff.name }
    if buff.stacking == StackType.INTENSITY:
        data["stacks"] = buff.capacity
    data["icon"] = static("raidar/img/buff/%s.png" % buff.code)
    return data

def _html_response(request, page, data={}):
    response = _userprops(request)
    response.update(data)
    try:
        response['ga_property_id'] = settings.GA_PROPERTY_ID
    except:
        # No Google Analytics, it's fine
        pass
    response['archetypes'] = {k: v for k, v in Participation.ARCHETYPE_CHOICES}
    response['areas'] = {id: {
            "name": boss.name,
            "kind": boss.kind,
        } for id, boss in BOSSES.items()}
    response['boss_locations'] = BOSS_LOCATIONS
    response['specialisations'] = {p: {e: n for (pp, e), n in SPECIALISATIONS.items() if pp == p} for p in Profession}
    response['categories'] = {category.id: category.name for category in Category.objects.all()}
    response['buffs'] = { buff.code: _buff_data(buff) for buff in BUFF_TYPES }
    response['buff_tabs'] = BUFF_TABS
    response['page'] = page
    response['debug'] = settings.DEBUG
    response['version'] = settings.VERSION
    if request.user.is_authenticated:
        response['privacy'] = request.user.user_profile.privacy
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
def download(request, url_id=None):
    if not hasattr(settings, 'UPLOAD_DIR'):
        return Http404("Not allowed")

    encounter = Encounter.objects.get(url_id=url_id)
    if request.user.is_authenticated:
        own_account_names = [account.name for account in Account.objects.filter(
            participations__encounter_id=encounter.id,
            user=request.user)]
    else:
        own_account_names = []
    dump = encounter.val
    members = [{ "name": name, **value } for name, value in dump['Category']['status']['Player'].items() if 'account' in value]

    encounter_showable = True
    for member in members:
        is_self = member['account'] in own_account_names

        user_profile = UserProfile.objects.filter(user__accounts__name=member['account'])
        if user_profile:
            privacy = user_profile[0].privacy
        else:
            privacy = UserProfile.SQUAD
        if not is_self and (privacy == UserProfile.PRIVATE or (privacy == UserProfile.SQUAD and not own_account_names)):
            encounter_showable = False

    path = encounter.diskname()
    if isfile(path) and (encounter_showable or request.user.is_staff):
        response = HttpResponse(open(path, 'rb'), content_type='application/vnd.ms-excel')
        response['Content-Disposition'] = 'attachment; filename="%s"' % encounter.filename
        return response
    else:
        raise Http404("Not allowed")


@require_GET
def index(request, page={ 'name': '' }):
    return _html_response(request, page)


def _add_build_data_to_profile(kind, data, profile):
    if 'encounter' not in profile or kind not in profile['encounter'] or 'All' not in data:
        return
    data = data['All']

    for archetype, archdata in profile['encounter'][kind]['archetype'].items():
        for profession, profdata in archdata['profession'].items():
            for elite, elitedata in profdata['elite'].items():
                builddata = _safe_get(lambda: data['build'][profession][elite][archetype])
                if builddata:
                    elitedata['everyone'] = builddata
    profile['encounter'][kind]['individual'] = data['individual']

def _profile_data_for_era(era_user_store):
    era = era_user_store.era
    era_val = era.val
    profile = era_user_store.val

    for era_area_store in EraAreaStore.objects.filter(era=era):
        _add_build_data_to_profile(str(era_area_store.area_id), era_area_store.val, profile)
    for kind, kind_data in era_val['kind'].items():
        _add_build_data_to_profile(kind, kind_data, profile)

    return {
        'id': era_user_store.era_id,
        'name': era.name,
        'started_at': era.started_at,
        'description': era.description,
        'profile': profile,
    }

@require_GET
def profile(request):
    if not request.user.is_authenticated:
        return _error("Not authenticated")

    user = request.user
    queryset = EraUserStore.objects.filter(user=user).select_related('era')
    try:
        eras = { era_user_store.era.id: _profile_data_for_era(era_user_store) for era_user_store in queryset}
    except EraUserStore.DoesNotExist:
        eras = {}

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
def global_stats(request, era_id=None, stats_page=None, json=None):
    if stats_page is None:
        stats_page = 'All raid bosses'

    if not json:
        return _html_response(request, {
            "name": "global_stats",
            "era_id": era_id,
            "stats_page": stats_page
        })
    try:
        era_query = Era.objects.all()
        eras = {era.id: {
                'name': era.name,
                'id': era.id,
                'started_at': era.started_at,
                'description': era.description
            } for era in era_query}
    except Era.DoesNotExist:
        eras = {}

    try:
        area_query = Area.objects.filter(era_area_stores__isnull = False).distinct()
        areas = [{
                'name': area.name,
                'id': area.id,
            } for area in area_query]
    except Area.DoesNotExist:
        areas = []

    try:
        if era_id is None:
            era_id = max(eras.values(), key=lambda z: z['started_at'])['id']
        era = Era.objects.get(id=era_id)

        try:
            area = Area.objects.get(id=int(stats_page))
            raw_data = EraAreaStore.objects.get(era=era, area=area).val
        except:
            raw_data = era.val["kind"].get(stats_page, {})

        stats = raw_data['All']

        #reduce size of json for global stats view
        builds = [stats['build'][prof][elite][arch]
                  for prof in stats['build']
                  for elite in stats['build'][prof]
                  for arch in stats['build'][prof][elite]]

        builds.append(stats['group'])
        builds.append(stats['individual'])

        for build in list(builds):
            if 'buffs' in build:
                del build['buffs']
            if 'count' not in build or build['count'] < 10:
                for key in list(build.keys()):
                    del(build[key])

            if 'buffs_out' in build:
                for buff in list(filter(lambda a: a.startswith('max_'), build['buffs_out'].keys())):
                    if build['buffs_out'][buff] <= 0.01:
                        buffname = buff[4:]
                        for key in list(filter(lambda a: a.split('_', 1)[1] == buffname,
                                        build['buffs_out'].keys())):
                            del(build['buffs_out'][key])

    except (Era.DoesNotExist, Area.DoesNotExist, EraAreaStore.DoesNotExist, KeyError):
        stats = {}

    result = {'global_stats': {
        'eras': eras,
        'areas': areas,
        'stats': stats
    }}
    return JsonResponse(result)


@require_GET
def leaderboards(request):
    kind = int(request.GET.get('kind', 0))
    bosses = [boss for wing in BOSS_LOCATIONS[kind]["wings"] for boss in wing["bosses"]]
    era_id = request.GET.get('era')
    eras = list(Era.objects.order_by('-started_at').values('id', 'name'))
    if not era_id:
        era_id = eras[0]['id']
    area_leaderboards = {}
    for area_id in bosses:
        try:
            leaderboards = EraAreaStore.objects.get(area_id=area_id, era_id=era_id).leaderboards
        except EraAreaStore.DoesNotExist:
            leaderboards = {}
        area_leaderboards[area_id] = leaderboards
    area_leaderboards['eras'] = eras
    area_leaderboards['era'] = era_id
    area_leaderboards['kind'] = kind
    result = {
            'leaderboards': area_leaderboards,
            'page.era': era_id,
            }
    return JsonResponse(result)


@require_GET
def encounter(request, url_id=None, json=None):
    try:
        encounter = Encounter.objects.select_related('area', 'uploaded_by').get(url_id=url_id)
    except Encounter.DoesNotExist:
        if json:
            return _error("Encounter does not exist")
        else:
            raise Http404("Encounter does not exist")
    own_account_names = [account.name for account in Account.objects.filter(
        participations__encounter_id=encounter.id,
        user=request.user)] if request.user.is_authenticated else []

    dump = encounter.val
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
                            "shielded": _safe_get(lambda: dump['Category']['combat']['Phase'][phase]['Subgroup'][str(party)]['Metrics']['shielded']['From']['*All']),
                            "buffs": _safe_get(lambda: dump['Category']['combat']['Phase'][phase]['Subgroup'][str(party)]['Metrics']['buffs']['From']['*All']),
                            "buffs_out": _safe_get(lambda: dump['Category']['combat']['Phase'][phase]['Subgroup'][str(party)]['Metrics']['buffs']['To']['*All']),
                            "events": _safe_get(lambda: dump['Category']['combat']['Phase'][phase]['Subgroup'][str(party)]['Metrics']['events']),
                            "mechanics": _safe_get(lambda: dump['Category']['combat']['Phase'][phase]['Subgroup'][str(party)]['Metrics']['mechanics']),
                        } for phase in phases
                    }
                } for party, members in groupby(sorted(members, key=partyfunc), partyfunc) }
    private = False

    encounter_showable = True
    for party_no, party in parties.items():
        for member in party['members']:
            if member['account'] in own_account_names:
                member['self'] = True
            member['phases'] = {
                phase: {
                    'actual': _safe_get(lambda: dump['Category']['combat']['Phase'][phase]['Player'][member['name']]['Metrics']['damage']['To']['*All']),
                    'actual_boss': _safe_get(lambda: dump['Category']['combat']['Phase'][phase]['Player'][member['name']]['Metrics']['damage']['To']['*Boss']),
                    'received': _safe_get(lambda: dump['Category']['combat']['Phase'][phase]['Player'][member['name']]['Metrics']['damage']['From']['*All']),
                    'shielded': _safe_get(lambda: dump['Category']['combat']['Phase'][phase]['Player'][member['name']]['Metrics']['shielded']['From']['*All']),
                    'buffs': _safe_get(lambda: dump['Category']['combat']['Phase'][phase]['Player'][member['name']]['Metrics']['buffs']['From']['*All']),
                    'buffs_out': _safe_get(lambda: dump['Category']['combat']['Phase'][phase]['Player'][member['name']]['Metrics']['buffs']['To']['*All']),
                    'events': _safe_get(lambda: dump['Category']['combat']['Phase'][phase]['Player'][member['name']]['Metrics']['events']),
                    'mechanics': _safe_get(lambda: dump['Category']['combat']['Phase'][phase]['Player'][member['name']]['Metrics']['mechanics']),
                    'archetype': _safe_get(lambda: area_stats[phase]['build'][str(member['profession'])][str(member['elite'])][str(member['archetype'])]),
                } for phase in phases
            }

            user_profile = UserProfile.objects.filter(user__accounts__name=member['account'])
            if user_profile:
                privacy = user_profile[0].privacy
            else:
                privacy = UserProfile.SQUAD
            if 'self' not in member and (privacy == UserProfile.PRIVATE or (privacy == UserProfile.SQUAD and not own_account_names)):
                member['name'] = ''
                member['account'] = ''
                private = True
                encounter_showable = False

    max_player_dps = max(_safe_get(lambda: data['Metrics']['damage']['To']['*All']['dps']) for phasename, phase in dump['Category']['combat']['Phase'].items() for player, data in phase['Player'].items())
    max_player_recv = max(_safe_get(lambda: data['Metrics']['damage']['From']['*All']['total']) for phasename, phase in dump['Category']['combat']['Phase'].items() for player, data in phase['Player'].items())

    data = {
        "encounter": {
            "evtc_version": _safe_get(lambda: dump['Category']['encounter']['evtc_version']),
            "id": encounter.id,
            "url_id": encounter.url_id,
            "name": encounter.area.name,
            "filename": encounter.filename,
            "uploaded_at": encounter.uploaded_at,
            "uploaded_by": encounter.uploaded_by.username,
            "started_at": encounter.started_at,
            "duration": encounter.duration,
            "success": encounter.success,
            "tags": encounter.tagstring,
            "category": encounter.category_id,
            "phase_order": phases,
            "participated": own_account_names != [],
            "boss_metrics": [metric.__dict__ for metric in BOSSES[encounter.area_id].metrics],
            "max_player_dps": max_player_dps,
            "max_player_recv": max_player_recv,
            "phases": {
                phase: {
                    'duration': encounter.duration if phase == "All" else _safe_get(lambda: dump['Category']['encounter']['Phase'][phase]['duration']),
                    'group': _safe_get(lambda: area_stats[phase]['group']),
                    'individual': _safe_get(lambda: area_stats[phase]['individual']),
                    'actual': _safe_get(lambda: dump['Category']['combat']['Phase'][phase]['Subgroup']['*All']['Metrics']['damage']['To']['*All']),
                    'actual_boss': _safe_get(lambda: dump['Category']['combat']['Phase'][phase]['Subgroup']['*All']['Metrics']['damage']['To']['*Boss']),
                    'received': _safe_get(lambda: dump['Category']['combat']['Phase'][phase]['Subgroup']['*All']['Metrics']['damage']['From']['*All']),
                    'shielded': _safe_get(lambda: dump['Category']['combat']['Phase'][phase]['Subgroup']['*All']['Metrics']['shielded']['From']['*All']),
                    'buffs': _safe_get(lambda: dump['Category']['combat']['Phase'][phase]['Subgroup']['*All']['Metrics']['buffs']['From']['*All']),
                    'buffs_out': _safe_get(lambda: dump['Category']['combat']['Phase'][phase]['Subgroup']['*All']['Metrics']['buffs']['To']['*All']),
                    'events': _safe_get(lambda: dump['Category']['combat']['Phase'][phase]['Subgroup']['*All']['Metrics']['events']),
                    'mechanics': _safe_get(lambda: dump['Category']['combat']['Phase'][phase]['Subgroup']['*All']['Metrics']['mechanics']),
                } for phase in phases
            },
            "parties": parties,
        }
    }

    if encounter_showable or request.user.is_staff:
        if encounter.gdrive_url:
            data['encounter']['evtc_url'] = encounter.gdrive_url;
        # XXX relic TODO remove once we fully cross to GDrive?
        if hasattr(settings, 'UPLOAD_DIR'):
            path = encounter.diskname()
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


@sensitive_variables('password')
def _perform_login(request):
    username = request.POST.get('username')
    password = request.POST.get('password')
    # stayloggedin = request.GET.get('stayloggedin')
    # if stayloggedin == "true":
    #     pass
    # else:
    #     request.session.set_expiry(0)

    return authenticate(username=username, password=password)


@require_POST
@sensitive_post_parameters('password')
def login(request):
    if request.method == 'GET':
        return index(request, page={ 'name': 'login' })

    user = _perform_login(request)
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


def _perform_upload(request):
    if (len(request.FILES) != 1):
        return ("Only single file uploads are allowed", None)

    if 'file' in request.FILES:
        file = request.FILES['file']
    else:
        return ("Missing file attachment named `file`", None)
    filename = file.name

    val = {}
    if 'category' in request.POST:
        val['category_id'] = request.POST['category']
    if 'tags' in request.POST:
        val['tagstring'] = request.POST['tags']

    uploaded_at = time()

    upload, _ = Upload.objects.update_or_create(
            filename=filename, uploaded_by=request.user,
            defaults={
                "uploaded_at": time(),
                "val": val,
            })

    diskname = upload.diskname()
    makedirs(dirname(diskname), exist_ok=True)
    with open(diskname, 'wb') as diskfile:
        while True:
            buf = file.read(16384)
            if len(buf) == 0:
                break
            diskfile.write(buf)
    return (filename, upload)


@login_required
@require_POST
def upload(request):
    filename, upload = _perform_upload(request)
    if not upload:
        return _error(filename)

    return JsonResponse({"filename": filename, "upload_id": upload.id})

@csrf_exempt
@require_POST
@sensitive_post_parameters('password')
def api_upload(request):
    try:
        user = _perform_login(request)
        if not user:
            return _error('Could not authenticate', status=401)
        auth_login(request, user)
        filename, upload = _perform_upload(request)
        if not upload:
            return _error(filename, status=400)

        return JsonResponse({"filename": filename, "upload_id": upload.id})

    except UnreadablePostError as e:
        return _error(e)

@csrf_exempt
def api_categories(request):
    categories = Category.objects.all()
    result = { category.id: category.name for category in categories }
    return JsonResponse(result)

@login_required
@require_POST
def profile_graph(request):
    era_id = request.POST['era']
    area_id = request.POST['area']
    archetype_id = request.POST['archetype']
    profession_id = request.POST['profession']
    elite_id = request.POST['elite']
    stat = request.POST['stat']

    participations = Participation.objects.select_related('encounter').filter(
            encounter__era_id=era_id, account__user=request.user, encounter__success=True)

    try:
        if area_id.startswith('All'):
            store = Era.objects.get(pk=era_id).val[area_id]
        else:
            participations = participations.filter(encounter__area_id=area_id)
            store = EraAreaStore.objects.get(era_id=era_id, area_id=area_id).val
    except (EraAreaStore.DoesNotExist, Era.DoesNotExist, KeyError):
        store = {}
    if archetype_id != 'All':
        participations = participations.filter(archetype=archetype_id)
    if profession_id != 'All':
        participations = participations.filter(profession=profession_id)
    if elite_id != 'All':
        participations = participations.filter(elite=elite_id)

    try:
        requested = store['All']['build'][profession_id][elite_id][archetype_id]
        requested = {
                'avg': requested['avg_' + stat],
                'per': list(np.frombuffer(base64.b64decode(requested['per_' + stat].encode('utf-8')), dtype=np.float32).astype(float)),
            }
    except KeyError:
        requested = None # XXX fill out in restat
    MAX_GRAPH_ENCOUNTERS = 50 # XXX move to top or to settings
    db_data = participations.order_by('-encounter__started_at')[:MAX_GRAPH_ENCOUNTERS].values_list('character', 'encounter__started_at', 'encounter__value')
    data = []
    times = []

    if stat == 'dps_boss':
        target = '*Boss'
        stat = 'dps'
    else:
        target = '*All'
    for name, started_at, json in reversed(db_data):
        dump = json_loads(json)
        datum = _safe_get(lambda: dump['Category']['combat']['Phase']['All']['Player'][name]['Metrics']['damage']['To'][target][stat], 0)
        data.append(datum)
        times.append(started_at)

    result = {
        'globals': requested,
        'data': data,
        'times': times,
    }
    return JsonResponse(result)


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

    result = {
        "notifications": [notification.val for notification in notifications],
        "version": settings.VERSION['id'],
    }
    if notifications:
        result['last_id'] = notifications.last().id
    return JsonResponse(result)

@login_required
@require_POST
def privacy(request):
    profile = request.user.user_profile
    profile.privacy = int(request.POST.get('privacy'))
    profile.save()
    return JsonResponse({})

@login_required
@require_POST
def set_tags_cat(request):
    encounter = Encounter.objects.get(pk=int(request.POST.get('id')))
    participation = encounter.participations.filter(account__user=request.user).exists()
    if not participation:
        return _error('Not a participant')
    encounter.tagstring = request.POST.get('tags')
    encounter.category_id = request.POST.get('category')
    encounter.save()
    return JsonResponse({})

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
