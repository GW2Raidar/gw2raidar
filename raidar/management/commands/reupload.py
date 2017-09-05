#from analyser.analyser import Analyser, Group, Archetype, EvtcAnalysisException
#from Crypto import Random
#from multiprocessing import Queue, Process, log_to_stderr
#from contextlib import contextmanager
from django.core.management.base import BaseCommand, CommandError
#from django.db import transaction
#from django.db.utils import IntegrityError
#from evtcparser.parser import Encounter as EvtcEncounter, EvtcParseException
#from gw2raidar import settings
#from json import loads as json_loads, dumps as json_dumps
from raidar.models import *
#from sys import exit, stderr
from time import time
#from zipfile import ZipFile, BadZipFile
#from queue import Empty
import os
import os.path
import logging
import re
#import signal
#from traceback import format_exc


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class Command(BaseCommand):
    help = 'Reupload EVTC files'

    def add_arguments(self, parser):
        parser.add_argument('files',
            nargs='+',
            help='EVTC files to reupload')

    def handle(self, *args, **options):
        start = time()
        self.reupload(*args, **options)
        end = time()

        if options['verbosity'] >= 3:
            print()
            print("Completed in %ss" % (end - start))

    def reupload(self, *args, **options):
        files = set(re.sub(r'\.error', '', file) for file in options['files'])
        for filename in files:
            try:
                with open(filename + '.error', 'r') as f:
                    orig_name, username = f.readline().rstrip().split(' ', 1)
                    username = username[1:-1]
            except FileNotFoundError:
                continue

            user = User.objects.get(username=username)
            upload_time = os.path.getmtime(filename)
            upload, _ = Upload.objects.update_or_create(
                    filename=orig_name, uploaded_by=user,
                    defaults={ "uploaded_at": upload_time })
            diskname = upload.diskname()
            os.makedirs(os.path.dirname(diskname), exist_ok=True)
            os.rename(filename, diskname)
            os.remove(filename + '.error')
