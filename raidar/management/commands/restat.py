from ._qsetiter import queryset_iterator
from collections import defaultdict
from contextlib import contextmanager
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.utils import IntegrityError
from gw2raidar import settings
from json import loads as json_loads, dumps as json_dumps
from os.path import join as path_join
from raidar.models import *
from sys import exit
from time import time
import os


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

    new_encounters = Encounter.objects.filter(uploaded_at__gte=last_run).count()
    if not (new_encounters or force):
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
            totals = self.calculate_stats(*args, **options)
            end = time()

            if options['verbosity'] >= 2:
                import pprint
                pp = pprint.PrettyPrinter(indent=2)
                pp.pprint(totals)

            if options['verbosity'] >= 3:
                print()
                print("Completed in %ss" % (end - start))

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
