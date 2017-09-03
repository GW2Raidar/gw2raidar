from analyser.analyser import Analyser, Group, Archetype, EvtcAnalysisException
from multiprocessing import Queue, Process, log_to_stderr
from contextlib import contextmanager
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.utils import IntegrityError
from evtcparser.parser import Encounter as EvtcEncounter, EvtcParseException
from gw2raidar import settings
from json import loads as json_loads, dumps as json_dumps
from raidar.models import *
from sys import exit, stderr
from time import time
from zipfile import ZipFile
from queue import Empty
import os
import logging
import signal


logger = log_to_stderr()
logger.setLevel(logging.INFO)

# inspired by https://stackoverflow.com/a/31464349/240443
class GracefulKiller:
    def __init__(self, queue):
        signal.signal(signal.SIGINT, self.exit_gracefully)
        signal.signal(signal.SIGTERM, self.exit_gracefully)
        self.queue = queue

    def exit_gracefully(self, signum, frame):
        logger.info('clearing the queue')
        try:
            while True:
                self.queue.get_nowait()
        except Empty:
            pass
    


# Google Drive
# pip install --upgrade google-api-python-client

gdrive_service = None
if hasattr(settings, 'GOOGLE_CREDENTIAL_FILE'):
    try:
        from oauth2client.service_account import ServiceAccountCredentials
        from httplib2 import Http
        from apiclient import discovery
        from googleapiclient.http import MediaFileUpload
        from googleapiclient.errors import HttpError

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


if hasattr(settings, 'UPLOAD_DIR'):
    upload_dir = settings.UPLOAD_DIR
else:
    upload_dir = 'uploads'


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


class Command(BaseCommand):
    help = 'Processes the uploads'

    def add_arguments(self, parser):
        parser.add_argument('-p', '--processes',
            type=int,
            dest='processes',
            default=1,
            help='Number of parallel processes')
        parser.add_argument('-l', '--limit',
            type=int,
            dest='limit',
            help='Limit of uploads to process')

    def handle(self, *args, **options):
        with single_process('restat'):
            start = time()
            self.analyse_uploads(*args, **options)
            self.clean_up(*args, **options)
            end = time()

            if options['verbosity'] >= 3:
                print()
                print("Completed in %ss" % (end - start))

    def analyse_uploads(self, *args, **options):
        new_uploads = Upload.objects.order_by('-filename')
        if 'limit' in options:
            new_uploads = new_uploads[:options['limit']]

        queue = Queue(len(new_uploads))
        killer = GracefulKiller(queue)

        for upload in new_uploads:
            queue.put(upload)

        process_pool = []
        for i in range(options['processes']):
            process = Process(target=self.analyse_upload_worker, args=(queue,))
            process.start()

        for process in process_pool:
            process.join()

    def analyse_upload_worker(self, queue):
        try:
            while True:
                upload = queue.get_nowait()
                logger.info(upload)
                self.analyse_upload(upload)
        except Empty:
            logger.info("done")

    def analyse_upload(self, upload):
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
            uploader = upload.uploaded_by

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
                            "uploaded_by": upload.uploaded_by.username,
                            "filename": upload.filename,
                            "encounter_id": encounter.id,
                            "encounter_url_id": encounter.url_id,
                            "encounter": participation.data(),
                        })
                        if uploader and account.user_id == uploader.id:
                            uploader = None

            if uploader:
                Notification.objects.create(user=uploader, val={
                    "type": "upload",
                    "upload_id": upload.id,
                    "uploaded_by": upload.uploaded_by.username,
                    "filename": upload.filename,
                    "encounter_id": encounter.id,
                    "encounter_url_id": encounter.url_id,
                })

            if gdrive_service:
                media = MediaFileUpload(diskname, mimetype='application/prs.evtc')
                try:
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
                except HttpError as e:
                    print(e, file=stderr)
                    pass

        except (EvtcParseException, EvtcAnalysisException) as e:
            Notification.objects.create(user=upload.uploaded_by, val={
                "type": "upload_error",
                "upload_id": upload.id,
                "error": str(e),
            })

        finally:
            if zipfile:
                zipfile.close()

            if file:
                file.close()

            upload.delete()

    def clean_up(self, *args, **options):
        # delete Notifications older than 15s (assuming poll is every 10s)
        Notification.objects.filter(created_at__lt=time() - 15).delete()
