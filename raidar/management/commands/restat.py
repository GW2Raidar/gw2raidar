from contextlib import contextmanager
from django.core.management.base import BaseCommand
from django.db.utils import IntegrityError
from raidar.models import *
from sys import exit
from time import time
import os
from evtcparser.parser import AgentType
import numpy as np
import base64

# XXX DEBUG: uncomment to log SQL queries
# import logging
# l = logging.getLogger('django.db.backends')
# l.setLevel(logging.DEBUG)
# l.addHandler(logging.StreamHandler())


@contextmanager
def single_process(name):
    try:
        pid = os.getpid()
        # Uncomment to remove pid in case of having cancelled restat with Ctrl+C...
        # Variable.objects.get(key='%s_pid' % name).delete()
        pid_var = Variable.objects.create(key='%s_pid' % name, val=os.getpid())
        try:
            yield pid
        finally:
            pid_var.delete()
    except IntegrityError:
        # already running
        exit()


@contextmanager
def necessary():
    try:
        last_run = Variable.get('restat_last')
    except Variable.DoesNotExist:
        last_run = 0

    start = time()

    yield last_run

    # only if successful:
    Variable.set('restat_last', start)


class RestatException(Exception):
    pass


def delete_old_files():
    gb = 1024 * 1024 * 1024
    min_disk_avail = 10 * gb
    num_pruned = 0

    if hasattr(os, 'statvfs'):
        def is_there_space_now():
            fs_data = os.statvfs(settings.UPLOAD_DIR)
            disk_avail = fs_data.f_frsize * fs_data.f_bavail
            return disk_avail > min_disk_avail
    else:
        def is_there_space_now():
            # No protection from full disk on Windows
            return True

    if is_there_space_now():
        return num_pruned

    encounter_queryset = Encounter.objects.filter(has_evtc=True).order_by('started_at')
    for encounter in encounter_queryset.iterator():
        filename = encounter.diskname()
        if filename:
            try:
                os.unlink(filename)
                num_pruned += 1
            except FileNotFoundError:
                pass
        encounter.has_evtc = False
        encounter.save()
        if is_there_space_now():
            return num_pruned
    return num_pruned


# TODO: Complete overhaul for new model (Temporary, to test whether restat can be removed)
# TODO: Create db models for restat results (If necessary)
# TODO: Rebuild restat for new db layout (If necessary)
class Command(BaseCommand):
    help = 'Recalculates the stats'

    def add_arguments(self, parser):
        parser.add_argument('-f', '--force',
            action='store_true',
            dest='force',
            default=False,
            help='Force calculation even if no new Encounters')

        parser.add_argument('-p', '--percentile_samples',
                            action='store',
                            dest='percentile_samples',
                            type=int,
                            default=1000,
                            help='Indicates the maximum number of samples to store for percentile sampling')

    def handle(self, *args, **options):
        with single_process('restat'), necessary() as last_run:
            start = time()
            start_date = datetime.now()
            pruned_count = delete_old_files()
            era_count, area_count, user_count, new_encounter_count = calculate_stats(last_run, **options)
            end = time()
            end_date = datetime.now()

            if options['verbosity'] >= 1:
                print()
                print("Completed in %ss" % (end - start))
            
            if (new_encounter_count + pruned_count) > 0:
                RestatPerfStats.objects.create(
                    started_on=start_date,
                    ended_on=end_date,
                    number_users=user_count,
                    number_eras=era_count,
                    number_areas=area_count,
                    number_new_encounters=new_encounter_count,
                    number_pruned_evtcs=pruned_count,
                    was_force=options['force'])


def recalculate_era(era, encounters):
    areas = encounters.area_set.distinct()
    area_data = {}
    users = encounters.participation_set.account_set.distinct()
    user_data = {}

    # Update area data
    for encounter in era.encounter_set.filter(area_id__in=areas):
        data = encounter.json_dump(participated=True)
        for phase_name, phase_data in data["encounter"]["phases"]:
            if phase_name not in area_data:
                area_data[phase_name] = {"group": {"count": 0}, "individual": {"count": 0}, "build": {}}
            # TODO: Group data
            # TODO: Individual data
            # TODO: Build data

    # TODO: Update user data
    for encounter in era.encounter_set.filter(participation__account__in=users):
        data = encounter.json_dump(participated=True)

    return len(areas), len(users)


def calculate_stats(last_run, **options):
    era_count = 0
    area_count = 0
    user_count = 0
    encounter_count = 0
    for era in Era.objects.all():
        era_count += 1
        force_recalculation = "force" in options and options["force"]
        last_run_timestamp = 0 if force_recalculation else last_run
        encounters = Encounter.objects.filter(era=era, uploaded_at__gte=last_run_timestamp)
        if encounters:
            encounter_count = len(encounters)  # Fine because we're iterating over all of them anyway
            area_count, user_count = recalculate_era(era, encounters)
        elif options["verbosity"] >= 2:
            print("Skipped era %s" % era)
    return era_count, area_count, user_count, encounter_count
