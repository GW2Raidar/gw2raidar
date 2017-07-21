from django.core.management.base import BaseCommand, CommandError
from django.db.utils import IntegrityError
from django.db import transaction
from ._qsetiter import queryset_iterator
from contextlib import contextmanager
from raidar.models import *
from json import loads as json_loads, dumps as json_dumps
from sys import exit
import os
import errno
from collections import defaultdict
from time import time
from evtcparser.parser import Encounter as EvtcEncounter, EvtcParseException
from analyser.analyser import Analyser, Group, Archetype, EvtcAnalysisException
from gw2raidar import settings
from os.path import join as path_join
from os import sep as dirsep

# Google Drive
# pip install --upgrade google-api-python-client

gdrive_service = None
if hasattr(settings, 'GOOGLE_CREDENTIAL_FILE'):
    try:
        from oauth2client.service_account import ServiceAccountCredentials
        from httplib2 import Http
        from apiclient import discovery
        from googleapiclient.http import MediaFileUpload

        scopes = ['https://www.googleapis.com/auth/drive.file']
        credentials = ServiceAccountCredentials.from_json_keyfile_name(
                settings.GOOGLE_CREDENTIAL_FILE, scopes=scopes)
        http_auth = credentials.authorize(Http())
        gdrive_service = discovery.build('drive', 'v3', http=http_auth)

        try:
            gdrive_folder = Variable.get('gdrive_folder')
        except Variable.DoesNotExist:
            metadata = {
                'name' : 'GW2 Raidar Files',
                'mimeType' : 'application/vnd.google-apps.folder'
            }
            folder = gdrive_service.files().create(
                    body=metadata, fields='id').execute()
            gdrive_folder = folder.get('id')

            permission = {
                'role': 'reader',
                'type': 'anyone',
                'allowFileDiscovery': False
            }
            result = gdrive_service.permissions().create(
                fileId=gdrive_folder,
                body=permission,
                fields='id',
            ).execute()

            Variable.set('gdrive_folder', gdrive_folder)
    except ImportError:
        pass

# XXX DEBUG
# import logging
# l = logging.getLogger('django.db.backends')
# l.setLevel(logging.DEBUG)
# l.addHandler(logging.StreamHandler())


@contextmanager
def single_process(name):
    try:
        pid = os.getpid()
        pid_var = Variable.objects.create(key='%s_pid' % name, val=os.getpid())
    except IntegrityError:
        # already running
        exit()

    try:
        yield pid
    finally:
        pid_var.delete()

@contextmanager
def necessary(force=False):
    try:
        last_run = Variable.get('restat_last')
    except Variable.DoesNotExist:
        last_run = 0

    start = time()

    new_uploads = Upload.objects.filter(uploaded_at__gte=last_run).count()
    new_encounters = Encounter.objects.filter(uploaded_at__gte=last_run).count()
    if not (new_uploads or new_encounters or force):
        exit()

    yield last_run

    # only if successful:
    Variable.set('restat_last', start)


class RestatException(Exception):
    pass


def get_or_create(hash, prop, type=dict):
    if prop not in hash:
        hash[prop] = type()
    return hash[prop]

def get_or_create_then_increment(hash, prop, lookup, attr=None):
    if isinstance(lookup, dict):
        try:
            value = lookup[attr or prop]
        except KeyError:
            return
    else:
        value = lookup

    get_or_create(hash, prop, type(value))
    hash[prop] += value
    get_or_create(hash, 'num_' + prop, int)
    hash['num_' + prop] += 1

def find_bounds(hash, prop, lookup, attr=None):
    if isinstance(lookup, dict):
        try:
            value = lookup[attr or prop]
        except KeyError:
            return
    else:
        value = lookup

    maxprop = 'max_' + prop
    if maxprop not in hash or value > hash[maxprop]:
        hash[maxprop] = value

    minprop = 'min_' + prop
    if minprop not in hash or value < hash[minprop]:
        hash[minprop] = value

def calculate_average(hash, prop):
    if prop in hash:
        hash['avg_' + prop] = hash[prop] / hash['num_' + prop]
        del hash[prop]


def _safe_get(func, default=0):
    try:
        return func()
    except KeyError:
        return default

class Command(BaseCommand):
    help = 'Recalculates the stats'

    def add_arguments(self, parser):
        parser.add_argument('-f', '--force',
            action='store_true',
            dest='force',
            default=False,
            help='Force calculation even if no new Encounters')

    def handle(self, *args, **options):
        with single_process('restat'), necessary(options['force']) as last_run:
            start = time()
            self.analyse_uploads(last_run, *args, **options)
            totals = self.calculate_stats(*args, **options)
            end = time()

            if options['verbosity'] >= 2:
                import pprint
                pp = pprint.PrettyPrinter(indent=2)
                pp.pprint(totals)

            if options['verbosity'] >= 3:
                print()
                print("Completed in %ss" % (end - start))

    def analyse_uploads(self, last_run, *args, **options):
        if hasattr(settings, 'UPLOAD_DIR'):
            upload_dir = settings.UPLOAD_DIR
        else:
            upload_dir = 'uploads'

        new_uploads = Upload.objects.filter(uploaded_at__gte=last_run)
        for upload in new_uploads:
            diskname = upload.diskname()
            zipfile = None
            file = None

            try:
                if upload.filename.endswith('.evtc.zip'):
                    zipfile = ZipFile(diskname)
                    contents = zipfile.infolist()
                    if len(contents) == 1:
                        file = zipfile.open(contents[0].filename)
                    else:
                        raise EvtcParseException('Only single-file ZIP archives are allowed')
                else:
                    file = open(diskname, 'rb')

                evtc_encounter = EvtcEncounter(file)
                analyser = Analyser(evtc_encounter)

                dump = analyser.data

                started_at = dump['Category']['encounter']['start']
                duration = dump['Category']['encounter']['duration']
                success = dump['Category']['encounter']['success']
                if duration < 60:
                    raise EvtcAnalysisException('Encounter shorter than 60s')

                era = Era.by_time(started_at)
                area = Area.objects.get(id=evtc_encounter.area_id)
                if not area:
                    raise EvtcAnalysisException('Unknown area')

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
                        encounter.era = era
                        encounter.filename = upload.filename
                        encounter.uploaded_at = upload.uploaded_at
                        encounter.uploaded_by = upload.uploaded_by
                        encounter.duration = duration
                        encounter.success = success
                        encounter.dump = json_dumps(dump)
                        encounter.started_at = started_at
                        encounter.started_at_full = started_at_full
                        encounter.started_at_half = started_at_half
                        encounter.save()
                    except Encounter.DoesNotExist:
                        encounter = Encounter.objects.create(
                            filename=upload.filename,
                            uploaded_at=upload.uploaded_at, uploaded_by=upload.uploaded_by,
                            duration=duration, success=success, dump=json_dumps(dump),
                            area=area, era=era, started_at=started_at,
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
                        if account.user:
                            Notification.objects.create(user=account.user, val={
                                "type": "upload",
                                "upload_id": upload.id,
                                "filename": upload.filename,
                                "encounter_id": encounter.id,
                                "encounter": participation.data(),
                            })

                if gdrive_service:
                    media = MediaFileUpload(diskname, mimetype='application/prs.evtc')
                    if encounter.gdrive_id:
                        result = gdrive_service.files().update(
                                fileId=encounter.gdrive_id,
                                media_body=media,
                            ).execute()
                    else:
                        metadata = {
                                'name': upload.filename,
                                'parents': [gdrive_folder],
                            }
                        gdrive_file = gdrive_service.files().create(
                                body=metadata, media_body=media,
                                fields='id, webContentLink',
                            ).execute()
                        encounter.gdrive_id = gdrive_file['id']
                        encounter.gdrive_url = gdrive_file['webContentLink']
                        encounter.save()

            except (EvtcParseException, EvtcAnalysisException) as e:
                Notification.objects.create(user=upload.uploaded_by, val={
                    "type": "upload_error",
                    "file": upload.filename,
                    "error": e
                })

            finally:
                if zipfile:
                    zipfile.close()

                if file:
                    file.close()

                upload.delete()


    def calculate_stats(self, *args, **options):
        totals = {
            "area": {},
            "character": {},
        }
        queryset = Encounter.objects.all()
        buffs = set()
        main_stats = ['dps', 'dps_boss', 'dps_received', 'total_received', 'crit', 'seaweed', 'scholar', 'flanking']
        for encounter in queryset_iterator(queryset):
            try:
                totals_in_area = get_or_create(totals['area'], encounter.area_id)
                data = json_loads(encounter.dump)
                phases = data['Category']['combat']['Phase']
                participations = encounter.participations.select_related('character').all()

                for phase, stats_in_phase in phases.items():
                    squad_stats_in_phase = stats_in_phase['Subgroup']['*All']
                    stats_in_phase_to_all = squad_stats_in_phase['Metrics']['damage']['To']['*All']
                    stats_in_phase_to_boss = squad_stats_in_phase['Metrics']['damage']['To']['*Boss']
                    stats_in_phase_received = _safe_get(lambda: squad_stats_in_phase['Metrics']['damage']['From']['*All'], {})
                    stats_in_phase_buffs = squad_stats_in_phase['Metrics']['buffs']
                    totals_in_phase = get_or_create(totals_in_area, phase)
                    group_totals = get_or_create(totals_in_phase, 'group')
                    individual_totals = get_or_create(totals_in_phase, 'individual')

                    buffs_by_party = get_or_create(group_totals, 'buffs')
                    for buff, value in squad_stats_in_phase['Metrics']['buffs']['From']['*All'].items():
                        find_bounds(buffs_by_party, buff, value)

                    # sums and averages, per encounter
                    if encounter.success:
                        get_or_create_then_increment(group_totals, 'dps', stats_in_phase_to_all)
                        get_or_create_then_increment(group_totals, 'dps_boss', stats_in_phase_to_boss, 'dps')
                        get_or_create_then_increment(group_totals, 'dps_received', stats_in_phase_received, 'dps')
                        get_or_create_then_increment(group_totals, 'total_received', stats_in_phase_received, 'total')
                        get_or_create_then_increment(group_totals, 'crit', stats_in_phase_to_all)
                        get_or_create_then_increment(group_totals, 'seaweed', stats_in_phase_to_all)
                        get_or_create_then_increment(group_totals, 'scholar', stats_in_phase_to_all)
                        get_or_create_then_increment(group_totals, 'flanking', stats_in_phase_to_all)

                        for buff, value in squad_stats_in_phase['Metrics']['buffs']['From']['*All'].items():
                            buffs.add(buff)
                            get_or_create_then_increment(buffs_by_party, buff, value)

                    # mins and maxes, per encounter
                    find_bounds(group_totals, 'dps', stats_in_phase_to_all)
                    find_bounds(group_totals, 'dps_boss', stats_in_phase_to_boss, 'dps')
                    find_bounds(group_totals, 'dps_received', stats_in_phase_received, 'dps')
                    find_bounds(group_totals, 'total_received', stats_in_phase_received, 'total')
                    find_bounds(group_totals, 'crit', stats_in_phase_to_all)
                    find_bounds(group_totals, 'seaweed', stats_in_phase_to_all)
                    find_bounds(group_totals, 'scholar', stats_in_phase_to_all)
                    find_bounds(group_totals, 'flanking', stats_in_phase_to_all)

                    totals_by_build = get_or_create(totals_in_phase, 'build')
                    for participation in participations:
                        # now per archetype

                        # XXX in case player did not actually participate (hopefully fix in analyser)
                        if (participation.character.name not in stats_in_phase['Player']):
                            continue
                        player_stats = stats_in_phase['Player'][participation.character.name]

                        totals_by_profession = get_or_create(totals_by_build, participation.character.profession)
                        elite = data['Category']['status']['Player'][participation.character.name]['elite']
                        totals_by_elite = get_or_create(totals_by_profession, elite)
                        totals_by_archetype = get_or_create(totals_by_elite, participation.archetype)

                        try:
                            # XXX what if DAMAGE TO *ALL is not there? (hopefully fix in analyser)
                            stats_in_phase_to_all = player_stats['Metrics']['damage']['To']['*All']

                            if encounter.success:
                                get_or_create_then_increment(totals_by_archetype, 'dps', stats_in_phase_to_all)
                                get_or_create_then_increment(totals_by_archetype, 'crit', stats_in_phase_to_all)
                                get_or_create_then_increment(totals_by_archetype, 'seaweed', stats_in_phase_to_all)
                                get_or_create_then_increment(totals_by_archetype, 'scholar', stats_in_phase_to_all)
                                get_or_create_then_increment(totals_by_archetype, 'flanking', stats_in_phase_to_all)

                            find_bounds(totals_by_archetype, 'dps', stats_in_phase_to_all)
                            find_bounds(individual_totals, 'dps', stats_in_phase_to_all)

                            find_bounds(totals_by_archetype, 'crit', stats_in_phase_to_all)
                            find_bounds(individual_totals, 'crit', stats_in_phase_to_all)

                            find_bounds(totals_by_archetype, 'seaweed', stats_in_phase_to_all)
                            find_bounds(individual_totals, 'seaweed', stats_in_phase_to_all)

                            find_bounds(totals_by_archetype, 'scholar', stats_in_phase_to_all)
                            find_bounds(individual_totals, 'scholar', stats_in_phase_to_all)

                            find_bounds(totals_by_archetype, 'flanking', stats_in_phase_to_all)
                            find_bounds(individual_totals, 'flanking', stats_in_phase_to_all)
                        except KeyError:
                            pass

                        try:
                            # XXX what if DAMAGE TO *BOSS is not there? (hopefully fix in analyser)
                            stats_in_phase_to_boss = player_stats['Metrics']['damage']['To']['*Boss']
                            if encounter.success:
                                get_or_create_then_increment(totals_by_archetype, 'dps_boss', stats_in_phase_to_boss, 'dps')
                            find_bounds(totals_by_archetype, 'dps_boss', stats_in_phase_to_boss, 'dps')
                            find_bounds(individual_totals, 'dps_boss', stats_in_phase_to_boss, 'dps')
                        except KeyError:
                            pass

                        try:
                            # XXX what if DAMAGE FROM *ALL is not there? (hopefully fix in analyser)
                            stats_in_phase_from_all = player_stats['Metrics']['damage']['From']['*All']
                            if encounter.success:
                                get_or_create_then_increment(totals_by_archetype, 'dps_received', stats_in_phase_from_all, 'dps')
                                get_or_create_then_increment(totals_by_archetype, 'total_received', stats_in_phase_from_all, 'total')
                            find_bounds(totals_by_archetype, 'dps_received', stats_in_phase_from_all, 'dps')
                            find_bounds(individual_totals, 'dps_received', stats_in_phase_from_all, 'dps')

                            find_bounds(totals_by_archetype, 'total_received', stats_in_phase_from_all, 'total')
                            find_bounds(individual_totals, 'total_received', stats_in_phase_from_all, 'total')
                        except KeyError:
                            pass

                        buffs_by_archetype = get_or_create(totals_by_archetype, 'buffs')
                        for buff, value in player_stats['Metrics']['buffs']['From']['*All'].items():
                            buffs.add(buff)
                            if encounter.success:
                                get_or_create_then_increment(buffs_by_archetype, buff, value)
                            find_bounds(buffs_by_archetype, buff, value)

            except:
                raise RestatException("Error in %s" % encounter)


        for area_id, totals_in_area in totals['area'].items():
            for phase, totals_in_phase in totals_in_area.items():
                group_totals = totals_in_phase['group']
                calculate_average(group_totals, 'dps')
                calculate_average(group_totals, 'dps_boss')
                calculate_average(group_totals, 'dps_received')
                calculate_average(group_totals, 'total_received')
                calculate_average(group_totals, 'crit')
                calculate_average(group_totals, 'seaweed')
                calculate_average(group_totals, 'scholar')
                calculate_average(group_totals, 'flanking')
                buffs_by_party = group_totals['buffs']
                for buff in buffs:
                    calculate_average(buffs_by_party, buff)
                for stat in main_stats:
                    calculate_average(group_totals, stat)

                for character_id, totals_by_build in totals_in_phase['build'].items():
                    for elite, totals_by_elite in totals_by_build.items():
                        for archetype, totals_by_archetype in totals_by_elite.items():
                            calculate_average(totals_by_archetype, 'dps')
                            calculate_average(totals_by_archetype, 'dps_boss')
                            calculate_average(totals_by_archetype, 'dps_received')
                            calculate_average(totals_by_archetype, 'total_received')
                            calculate_average(totals_by_archetype, 'crit')
                            calculate_average(totals_by_archetype, 'seaweed')
                            calculate_average(totals_by_archetype, 'scholar')
                            calculate_average(totals_by_archetype, 'flanking')
                            for stat in main_stats:
                                calculate_average(totals_by_archetype, stat)

                            buffs_by_archetype = totals_by_archetype['buffs']
                            for buff in buffs:
                                calculate_average(buffs_by_archetype, buff)

            Area.objects.filter(pk=area_id).update(stats=json_dumps(totals_in_area))

        return totals
