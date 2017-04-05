from django.core.management.base import BaseCommand, CommandError
from ._qsetiter import queryset_iterator
from raidar.models import *
from json import loads as json_loads, dumps as json_dumps
from sys import exit
import os
import errno
from collections import defaultdict

# XXX DEBUG
# import logging
# l = logging.getLogger('django.db.backends')
# l.setLevel(logging.DEBUG)
# l.addHandler(logging.StreamHandler())


SCRIPTDIR = os.path.dirname(os.path.realpath(__file__))
PIDFILE = os.path.join(SCRIPTDIR, 'restat.pid')

def get_or_create(hash, prop, type=dict):
    if prop not in hash:
        hash[prop] = type()
    return hash[prop]

def get_or_create_then_increment(hash, prop, value=1):
    get_or_create(hash, prop, type(value))
    hash[prop] += value

def find_bounds(hash, prop, value):
    maxprop = "max_" + prop
    if maxprop not in hash or value > hash[maxprop]:
        hash[maxprop] = value

    minprop = "min_" + prop
    if minprop not in hash or value < hash[minprop]:
        hash[minprop] = value

def calculate_average(hash, prop):
    if prop in hash:
        hash['avg_' + prop] = hash[prop] / hash['count']
        del hash[prop]

def check_running():
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
        with os.fdopen(file_handle, 'w') as f:
            f.write(str(os.getpid()))
        return False

class Command(BaseCommand):
    help = 'Recalculates the stats'

    def handle(self, *args, **options):
        if check_running():
            exit()
        try:
            self.process(*args, **options)
        finally:
            os.remove(PIDFILE)

    def process(self, *args, **options):
        totals = {
            "area": {},
            "character": {},
        }
        queryset = Encounter.objects.all()
        for encounter in queryset_iterator(queryset):
            totals_in_area = get_or_create(totals['area'], encounter.area_id)
            data = json_loads(encounter.dump)
            phases = data['Category']['damage']['Phase']
            participations = encounter.participations.select_related('character').all()

            for phase, stats_in_phase in phases.items():
                stats_in_phase_to_all = stats_in_phase['To']['*All']
                totals_in_phase = get_or_create(totals_in_area, phase)
                group_totals = get_or_create(totals_in_phase, 'group')
                individual_totals = get_or_create(totals_in_phase, 'individual')

                get_or_create_then_increment(group_totals, 'dps', stats_in_phase_to_all['dps'])
                find_bounds(group_totals, 'dps', stats_in_phase_to_all['dps'])
                get_or_create_then_increment(group_totals, 'seaweed', stats_in_phase_to_all['seaweed'])
                find_bounds(group_totals, 'seaweed', stats_in_phase_to_all['seaweed'])
                get_or_create_then_increment(group_totals, 'scholar', stats_in_phase_to_all['scholar'])
                find_bounds(group_totals, 'scholar', stats_in_phase_to_all['scholar'])

                # TODO: duration, damage_in, boss_damage
                get_or_create_then_increment(group_totals, 'count')

                totals_by_build = get_or_create(totals_in_phase, 'build')
                for participation in participations:
                    stats_in_phase_to_all = stats_in_phase['Player'][participation.character.name]['To']['*All']
                    totals_by_profession = get_or_create(totals_by_build, participation.character.profession)
                    elite = data['Category']['status']['Name'][participation.character.name]['elite']
                    totals_by_elite = get_or_create(totals_by_profession, elite)
                    totals_by_archetype = get_or_create(totals_by_elite, participation.archetype)

                    get_or_create_then_increment(totals_by_archetype, 'dps', stats_in_phase_to_all['dps'])
                    find_bounds(totals_by_archetype, 'dps', stats_in_phase_to_all['dps'])
                    find_bounds(individual_totals, 'dps', stats_in_phase_to_all['dps'])

                    get_or_create_then_increment(totals_by_archetype, 'seaweed', stats_in_phase_to_all['seaweed'])
                    find_bounds(totals_by_archetype, 'seaweed', stats_in_phase_to_all['seaweed'])
                    find_bounds(individual_totals, 'seaweed', stats_in_phase_to_all['seaweed'])

                    get_or_create_then_increment(totals_by_archetype, 'scholar', stats_in_phase_to_all['scholar'])
                    find_bounds(totals_by_archetype, 'scholar', stats_in_phase_to_all['scholar'])
                    find_bounds(individual_totals, 'scholar', stats_in_phase_to_all['scholar'])

                    # TODO: damage_in, boss_damage...
                    get_or_create_then_increment(totals_by_archetype, 'count')

        for area_id, totals_in_area in totals['area'].items():
            for phase, totals_in_phase in totals_in_area.items():
                group_totals = totals_in_phase['group']
                individual_totals = totals_in_phase['individual']
                calculate_average(group_totals, 'dps')
                calculate_average(group_totals, 'seaweed')
                calculate_average(group_totals, 'scholar')
                del group_totals['count']

                for character_id, totals_by_build in totals_in_phase['build'].items():
                    for elite, totals_by_elite in totals_by_build.items():
                        for archetype, totals_by_archetype in totals_by_elite.items():
                            calculate_average(totals_by_archetype, 'dps')
                            calculate_average(totals_by_archetype, 'seaweed')
                            calculate_average(totals_by_archetype, 'scholar')
                            del totals_by_archetype['count']

            Area.objects.filter(pk=area_id).update(stats=json_dumps(totals_in_area))

        # XXX DEBUG
        import pprint
        pp = pprint.PrettyPrinter(indent=2)
        pp.pprint(totals)
