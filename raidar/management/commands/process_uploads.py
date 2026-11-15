from django.db.models import Q
from analyser.analyser import EvtcAnalysisException
from analyser.bosses import Kind, Mode, find_boss, UnsupportedEncounter
from eiparser import adapter, runner
from eiparser.adapter import EIAdapterException
from eiparser.runner import EIParseException
from multiprocessing import Queue, Process, log_to_stderr
from contextlib import contextmanager
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.utils import IntegrityError
from gw2raidar import settings
from raidar.models import *
from sys import exit, stderr
from time import time
from zipfile import ZipFile, ZIP_DEFLATED, is_zipfile
from queue import Empty
import os
import os.path
import logging
import signal
from traceback import format_exc


logger = log_to_stderr()
logger.setLevel(logging.INFO)

COMPRESSED_EXTENSIONS = ('.evtc.zip', '.zevtc')


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
        if options.get('limit') is not None:
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
        # Elite Insights HTML report of the log; moved next to the stored log once the encounter is known
        report_diskname = diskname + ".html.gz"

        try:
            # Elite Insights reads .evtc, .evtc.zip and .zevtc directly, but reports a damaged archive as a crash
            if upload.filename.endswith(COMPRESSED_EXTENSIONS) and not is_zipfile(diskname):
                raise EvtcAnalysisException('File is not a valid archive')

            log = runner.parse(diskname,
                               getattr(settings, 'GW2EI_CLI', None),
                               timeout=getattr(settings, 'GW2EI_TIMEOUT', runner.DEFAULT_TIMEOUT),
                               report_path=report_diskname)
            dump = adapter.convert(log)
            del log

            uploader = upload.uploaded_by
            encounter_dump = dump['Category']['encounter']

            started_at = encounter_dump['start']
            duration = encounter_dump['duration']
            success = encounter_dump['success']
            upload_val = upload.val

            boss = find_boss(encounter_dump['ei_encounter_id'], encounter_dump['cm'], encounter_dump['legendary_cm'])
            area_id = boss.area_id

            minDuration = 60
            if boss.kind == Kind.FRACTAL:
                minDuration = 30

            if duration < minDuration:
                raise EvtcAnalysisException('Encounter shorter than %ds' % minDuration)

            era = Era.by_time(started_at)

            area, _ = Area.objects.get_or_create(id=area_id,
                    defaults={"name": boss.base_name, "is_cm": boss.mode == Mode.CM,
                              "is_lcm": boss.mode == Mode.LEGENDARY_CM})

            status_for = {name: player for name, player in dump['Category']['status']['Player'].items() if 'account' in player}
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
                is_compressed = filename.endswith(COMPRESSED_EXTENSIONS)
                encounter_data = EncounterData.from_dump(dump)
                if not is_compressed:
                    filename += ".zip"
                try:
                    encounter = Encounter.objects.get(
                        Q(started_at_full=started_at_full) | Q(started_at_half=started_at_half),
                        area=area, account_hash=account_hash
                    )
                    if encounter.has_evtc:
                        for old_filename in (encounter.diskname(), encounter.report_diskname()):
                            if old_filename:
                                try:
                                    os.remove(old_filename)
                                except FileNotFoundError:
                                    pass
                    encounter.era = era
                    encounter.filename = filename
                    encounter.uploaded_on = datetime.fromtimestamp(upload.uploaded_at, timezone.utc)
                    encounter.uploaded_by = upload.uploaded_by
                    encounter.duration = duration
                    encounter.success = success
                    encounter.encounter_data = encounter_data
                    encounter.started_at = started_at
                    encounter.started_at_full = started_at_full
                    encounter.started_at_half = started_at_half
                    encounter.has_evtc = True
                except Encounter.DoesNotExist:
                    encounter = Encounter.objects.create(
                        filename=filename,
                        uploaded_on=datetime.fromtimestamp(upload.uploaded_at, timezone.utc),
                        uploaded_by=upload.uploaded_by,
                        duration=duration, success=success, encounter_data=encounter_data,
                        area=area, era=era, started_at=started_at,
                        started_at_full=started_at_full, started_at_half=started_at_half,
                        has_evtc=True, account_hash=account_hash
                    )
                if 'category_id' in upload_val:
                    encounter.category_id = upload_val['category_id']
                if 'tagstring' in upload_val:
                    encounter.tagstring = upload_val['tagstring']
                encounter.save()

                new_diskname = encounter.diskname()
                os.makedirs(os.path.dirname(new_diskname), exist_ok=True)
                if is_compressed:
                    os.rename(diskname, new_diskname)
                else:
                    with ZipFile(new_diskname, 'w', ZIP_DEFLATED) as zipfile_out:
                        zipfile_out.write(diskname, orig_filename)
                os.replace(report_diskname, encounter.report_diskname())

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

            logger.info("saved")

        except (EIParseException, EIAdapterException, UnsupportedEncounter, EvtcAnalysisException) as e:
            logger.info("known error: %s" % str(e))
            Notification.objects.create(user=upload.uploaded_by, val={
                "type": "upload_error",
                "upload_id": upload.id,
                "error": str(e),
            })

        # for diagnostics and catching new exceptions
        # (includes runner.EIRunException: EI missing, crashed or timed out)
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
            # a report that was not moved to its encounter belongs to a failed upload
            try:
                os.remove(report_diskname)
            except OSError:
                pass
            upload.delete()

    def clean_up(self, *args, **options):
        # delete Notifications older than 45s (assuming poll is every 30s)
        Notification.objects.filter(created_at__lt=time() - 45).delete()
