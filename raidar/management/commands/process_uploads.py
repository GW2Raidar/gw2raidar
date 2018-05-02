from analyser.analyser import Analyser, Group, Archetype, EvtcAnalysisException
from analyser.bosses import *
from multiprocessing import Queue, Process, log_to_stderr
from contextlib import contextmanager
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.utils import IntegrityError
from evtcparser.parser import Encounter as EvtcEncounter, EvtcParseException
from gw2raidar import settings
from raidar.models import *
from sys import exit, stderr
from time import time
from zipfile import ZipFile, BadZipFile, ZIP_DEFLATED
from queue import Empty
import os
import os.path
import logging
import signal
from traceback import format_exc


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


# def get_gdrive_service():
#     return None

# gdrive_service = None
# if hasattr(settings, 'GOOGLE_CREDENTIAL_FILE'):
#     try:
#         from oauth2client.service_account import ServiceAccountCredentials
#         from httplib2 import Http
#         from apiclient import discovery
#         from googleapiclient.http import MediaFileUpload
#         from googleapiclient.errors import HttpError

#         def get_gdrive_service():
#             scopes = ['https://www.googleapis.com/auth/drive.file']
#             credentials = ServiceAccountCredentials.from_json_keyfile_name(
#                     settings.GOOGLE_CREDENTIAL_FILE, scopes=scopes)
#             http_auth = credentials.authorize(Http())
#             gdrive_service = discovery.build('drive', 'v3', http=http_auth)
#             return gdrive_service

#         gdrive_service = get_gdrive_service()

#         try:
#             gdrive_folder = Variable.get('gdrive_folder')
#         except Variable.DoesNotExist:
#             metadata = {
#                 'name' : 'GW2 Raidar Files',
#                 'mimeType' : 'application/vnd.google-apps.folder'
#             }
#             folder = gdrive_service.files().create(
#                     body=metadata, fields='id').execute()
#             gdrive_folder = folder.get('id')

#             permission = {
#                 'role': 'reader',
#                 'type': 'anyone',
#                 'allowFileDiscovery': False
#             }
#             result = gdrive_service.permissions().create(
#                 fileId=gdrive_folder,
#                 body=permission,
#                 fields='id',
#             ).execute()

#             Variable.set('gdrive_folder', gdrive_folder)
#     except ImportError:
#         pass


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
        with single_process('process_uploads'):
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

        from django import db
        db.connections.close_all()

        if options['processes'] > 1:
            process_pool = []
            for i in range(options['processes']):
                process = Process(target=self.analyse_upload_worker, args=(queue,))
                process_pool.append(process)
                process.start()

            for process in process_pool:
                process.join()
        else:
            self.analyse_upload_worker(queue, False)

    def analyse_upload_worker(self, queue, multi=True):
        if multi:
            from Crypto import Random
            Random.atfork()
        # self.gdrive_service = get_gdrive_service()
        try:
            while True:
                upload = queue.get_nowait()
                logger.info("starting %s (%s)" % (upload.filename, upload.diskname()))
                start = time()
                self.analyse_upload(upload)
                logger.info("finished in %.2fs" % (time() - start))
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
                    try:
                        file = zipfile.open(contents[0].filename)
                    except RuntimeError as e:
                        raise EvtcAnalysisException(e)
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
            boss_name = analyser.boss_info.name
            upload_val = upload.val
            area_id = evtc_encounter.area_id

            minDuration = 60
            if BOSSES[area_id].kind == Kind.FRACTAL:
                minDuration = 30    
            
            if duration < minDuration:
                raise EvtcAnalysisException('Encounter shorter than 60s')
                        
            if dump['Category']['encounter']['cm']:
                boss_name += " (CM)"
                if analyser.boss_info.non_cm_allowed:
                    area_id += 0xFF0000
                            
            era = Era.by_time(started_at)        
                
            area, _ = Area.objects.get_or_create(id=area_id,
                    defaults={ "name": boss_name })

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
                filename = upload.filename
                orig_filename = filename
                if not zipfile:
                    filename += ".zip"
                try:
                    encounter = Encounter.objects.get(
                        Q(started_at_full=started_at_full) | Q(started_at_half=started_at_half),
                        area=area, account_hash=account_hash
                    )
                    encounter.era = era
                    encounter.filename = filename
                    encounter.uploaded_at = upload.uploaded_at
                    encounter.uploaded_by = upload.uploaded_by
                    encounter.duration = duration
                    encounter.success = success
                    encounter.val = dump
                    encounter.started_at = started_at
                    encounter.started_at_full = started_at_full
                    encounter.started_at_half = started_at_half
                    encounter.has_evtc = True
                except Encounter.DoesNotExist:
                    encounter = Encounter.objects.create(
                        filename=filename,
                        uploaded_at=upload.uploaded_at, uploaded_by=upload.uploaded_by,
                        duration=duration, success=success, val=dump,
                        area=area, era=era, started_at=started_at,
                        started_at_full=started_at_full, started_at_half=started_at_half,
                        has_evtc=True, account_hash=account_hash
                    )
                if 'category_id' in upload_val:
                    encounter.category_id = upload_val['category_id']
                if 'tagstring' in upload_val:
                    encounter.tagstring = upload_val['tagstring']
                encounter.save()

                file.close()
                file = None
                new_diskname = encounter.diskname()
                os.makedirs(os.path.dirname(new_diskname), exist_ok=True)
                if zipfile:
                    zipfile.close()
                    zipfile = None
                    os.rename(diskname, new_diskname)
                else:
                    with ZipFile(new_diskname, 'w', ZIP_DEFLATED) as zipfile_out:
                        zipfile_out.write(diskname, orig_filename)

                for name, player in status_for.items():
                    account, _ = Account.objects.get_or_create(
                        name=player['account'])
                    participation, _ = Participation.objects.update_or_create(
                        account=account, encounter=encounter,
                        defaults={
                            'character': name,
                            'archetype': player['archetype'],
                            'profession': player['profession'],
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

            # if self.gdrive_service:
            #     media = MediaFileUpload(new_diskname, mimetype='application/prs.evtc')
            #     try:
            #         if encounter.gdrive_id:
            #             result = self.gdrive_service.files().update(
            #                     fileId=encounter.gdrive_id,
            #                     media_body=media,
            #                 ).execute()
            #         else:
            #             metadata = {
            #                     'name': upload.filename,
            #                     'parents': [gdrive_folder],
            #                 }
            #             gdrive_file = self.gdrive_service.files().create(
            #                     body=metadata, media_body=media,
            #                     fields='id, webContentLink',
            #                 ).execute()
            #             encounter.gdrive_id = gdrive_file['id']
            #             encounter.gdrive_url = gdrive_file['webContentLink']
            #             encounter.save()
            #     except HttpError as e:
            #         logger.error(e)
            #         pass
            #
            logger.info("saved")

        except (EvtcParseException, EvtcAnalysisException, BadZipFile) as e:
            logger.info("known error: %s" % str(e))
            Notification.objects.create(user=upload.uploaded_by, val={
                "type": "upload_error",
                "upload_id": upload.id,
                "error": str(e),
            })

        # for diagnostics and catching new exceptions
        except Exception as e:
            logger.info("unknown error: %s" % str(e))
            exc = format_exc()
            path = os.path.join(upload_dir, 'errors')
            os.makedirs(path, exist_ok=True)
            path = os.path.join(path, os.path.basename(diskname))
            os.rename(diskname, path)
            with open(path + '.error', 'w') as f:
                f.write("%s (%s)\n" % (upload.filename, upload.uploaded_by.username))
                f.write(exc)
            logger.error(exc)
            Notification.objects.create(user=upload.uploaded_by, val={
                "type": "upload_error",
                "upload_id": upload.id,
                "error": "An unexpected error has occured, and your file has been stored for inspection by the developers.",
            })

        finally:
            if file:
                file.close()

            if zipfile:
                zipfile.close()

            upload.delete()

    def clean_up(self, *args, **options):
        # delete Notifications older than 45s (assuming poll is every 30s)
        Notification.objects.filter(created_at__lt=time() - 45).delete()
