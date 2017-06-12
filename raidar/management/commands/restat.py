from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from ._qsetiter import queryset_iterator
from raidar.models import *
from json import loads as json_loads, dumps as json_dumps
from sys import exit
import os
import errno
from collections import defaultdict
from time import time

# XXX DEBUG
# import logging
# l = logging.getLogger('django.db.backends')
# l.setLevel(logging.DEBUG)
# l.addHandler(logging.StreamHandler())


PIDFILE = settings.RESTAT_PID_FILE

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

def check_running_or_unnecesary():
    # http://stackoverflow.com/questions/10978869
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    permissions = 0o644
    try:
        file_handle = os.open(PIDFILE, flags, permissions)
    except OSError as e:
        if e.errno == errno.EEXIST:
            return True
        else:
            raise
    else:
        try:
            last_restat_at = os.path.getmtime(PIDFILE + ".last")
        except FileNotFoundError:
            pass # last file being missing is okay
        else:
            new = Encounter.objects.filter(uploaded_at__gte=last_restat_at).count()
            if new > 0:
                with os.fdopen(file_handle, 'w') as f:
                    f.write(str(os.getpid()))
                return False
            else:
                return True

def _safe_get(func, default=0):
    try:
        return func()
    except KeyError:
        return default

class Command(BaseCommand):
    help = 'Recalculates the stats'

    def process(self, *args, **options):
        totals = {
            "area": {},
            "character": {},
        }
        queryset = Encounter.objects.all()
        buffs = set()
        for encounter in queryset_iterator(queryset):
            totals_in_area = get_or_create(totals['area'], encounter.area_id)
            data = json_loads(encounter.dump)
            phases = data['Category']['combat']['Phase']
            participations = encounter.participations.select_related('character').all()

            for phase, stats_in_phase in phases.items():
                squad_stats_in_phase = stats_in_phase['Subgroup']['*All']
                stats_in_phase_to_all = squad_stats_in_phase['Metrics']['damage']['To']['*All']
                stats_in_phase_to_boss = squad_stats_in_phase['Metrics']['damage']['To']['*Boss']
                stats_in_phase_received = _safe_get(lambda: squad_stats_in_phase['Metrics']['damage']['From']['*All'], {})
                stats_in_phase_buffs = squad_stats_in_phase['Metrics']['buffs']['From']['*All']
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

                    try:
                        # XXX what if DAMAGE TO *ALL is not there? (hopefully fix in analyser)
                        stats_in_phase_to_all = player_stats['Metrics']['damage']['To']['*All']
                        totals_by_profession = get_or_create(totals_by_build, participation.character.profession)
                        elite = data['Category']['status']['Player'][participation.character.name]['elite']
                        totals_by_elite = get_or_create(totals_by_profession, elite)
                        totals_by_archetype = get_or_create(totals_by_elite, participation.archetype)
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

                    if encounter.success:
                        get_or_create_then_increment(totals_by_archetype, 'dps', stats_in_phase_to_all)
                        get_or_create_then_increment(totals_by_archetype, 'seaweed', stats_in_phase_to_all)
                        get_or_create_then_increment(totals_by_archetype, 'scholar', stats_in_phase_to_all)
                        get_or_create_then_increment(totals_by_archetype, 'flanking', stats_in_phase_to_all)

                    find_bounds(totals_by_archetype, 'dps', stats_in_phase_to_all)
                    find_bounds(individual_totals, 'dps', stats_in_phase_to_all)

                    find_bounds(totals_by_archetype, 'seaweed', stats_in_phase_to_all)
                    find_bounds(individual_totals, 'seaweed', stats_in_phase_to_all)

                    find_bounds(totals_by_archetype, 'scholar', stats_in_phase_to_all)
                    find_bounds(individual_totals, 'scholar', stats_in_phase_to_all)

                    find_bounds(totals_by_archetype, 'flanking', stats_in_phase_to_all)
                    find_bounds(individual_totals, 'flanking', stats_in_phase_to_all)

                    buffs_by_archetype = get_or_create(totals_by_archetype, 'buffs')
                    for buff, value in player_stats['Metrics']['buffs']['From']['*All'].items():
                        buffs.add(buff)
                        if encounter.success:
                            get_or_create_then_increment(buffs_by_archetype, buff, value)
                        find_bounds(buffs_by_archetype, buff, value)


        for area_id, totals_in_area in totals['area'].items():
            for phase, totals_in_phase in totals_in_area.items():
                group_totals = totals_in_phase['group']
                individual_totals = totals_in_phase['individual']
                calculate_average(group_totals, 'dps')
                calculate_average(group_totals, 'dps_boss')
                calculate_average(group_totals, 'dps_received')
                calculate_average(group_totals, 'total_received')
                calculate_average(group_totals, 'seaweed')
                calculate_average(group_totals, 'scholar')
                calculate_average(group_totals, 'flanking')
                buffs_by_party = group_totals['buffs']
                for buff in buffs:
                    calculate_average(buffs_by_party, buff)

                for character_id, totals_by_build in totals_in_phase['build'].items():
                    for elite, totals_by_elite in totals_by_build.items():
                        for archetype, totals_by_archetype in totals_by_elite.items():
                            calculate_average(totals_by_archetype, 'dps')
                            calculate_average(totals_by_archetype, 'dps_boss')
                            calculate_average(totals_by_archetype, 'dps_received')
                            calculate_average(totals_by_archetype, 'total_received')
                            calculate_average(totals_by_archetype, 'seaweed')
                            calculate_average(totals_by_archetype, 'scholar')
                            calculate_average(totals_by_archetype, 'flanking')

                            buffs_by_archetype = totals_by_archetype['buffs']
                            for buff in buffs:
                                calculate_average(buffs_by_archetype, buff)

            Area.objects.filter(pk=area_id).update(stats=json_dumps(totals_in_area))

        return totals

    def handle(self, *args, **options):
        try:
            if check_running_or_unnecesary():
                exit()
            start = time()
            totals = self.process(*args, **options)
            end = time()

            import pprint
            pp = pprint.PrettyPrinter(indent=2)
            pp.pprint(totals)

            print()
            print("Completed in %ss" % (end - start))
        finally:
            os.rename(PIDFILE, PIDFILE + ".last")
