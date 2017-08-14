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

def get_and_add(hash, prop, n):
    get_or_create(hash, prop, float)
    hash[prop] += n

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

def navigate(node, *names):
    new_node = node
    for name in names:
        if name not in new_node:
            new_node[name] = dict()
        new_node = new_node[name]
    return new_node

def bound_stats(output, name, value):
    maxprop = 'max|' + name
    if maxprop not in output or value > output[maxprop]:
        output[maxprop] = value

    minprop = 'min|' + name
    if minprop not in output or value < output[minprop]:
        output[minprop] = value

def all_stats(output, name, value):
    find_bounds(output, name, value)
    average_stat(output, name, value)

def average_stat(output, name, value):
    output['avgsum|' + name] = output.get('avgsum|' + name, 0) + value
    output['avgnum|' + name] = output.get('avgnum|' + name, 0) + 1

def calculate_average(hash, prop):
    if prop in hash:
        hash['avg_' + prop] = hash[prop] / hash['num_' + prop]
        del hash[prop]


def _safe_get(func, default=0):
    try:
        return func()
    except (KeyError, TypeError):
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
            self.calculate_stats(*args, **options)
            end = time()

            if options['verbosity'] >= 3:
                print()
                print("Completed in %ss" % (end - start))

    def calculate_stats(self, *args, **options):
        main_stats = ['dps', 'dps_boss', 'dps_received', 'total_received', 'crit', 'seaweed', 'scholar', 'flanking']
        for era in Era.objects.all():
            # TODO: don't recalculate eras with no uploads
            totals = {
                "area": {},
                "user": {},
            }
            era_queryset = era.encounters.all()
            buffs = set()
            for encounter in queryset_iterator(era_queryset):
                participations = encounter.participations.select_related('character', 'character__account').all()

                try:
                    data = json_loads(encounter.dump)
                    duration = data['Category']['encounter']['duration'] * 1000
                    for participation in participations:
                        try:
                            player_stats = data['Category']['combat']['Phase']['All']['Player'][participation.character.name]
                            user_id = participation.character.account.user_id
                            # TODO if user_id: # (otherwise we're ignoring the person)
                            totals_for_player = navigate(totals['user'], user_id)
                            player_summary = navigate(totals_for_player, 'summary')

                            def categorise(split_encounter, split_archetype, split_profession):
                                return navigate(totals_for_player,
                                                'encounter', encounter.area_id if split_encounter else 'All',
                                                'archetype', participation.archetype if split_archetype else 'All',
                                                'profession', participation.character.profession if split_profession else 'All')
                            player_this_encounter = categorise(True, False, False)
                            player_this_archetype = categorise(False, True, False)
                            player_this_profession = categorise(False, False, True)
                            player_this_build = categorise(False, True, True)
                            player_archetype_encounter = categorise(True, True, False)
                            player_build_encounter = categorise(True, True, True)

                            get_and_add(totals_for_player, 'count', 1)

                            get_and_add(player_this_encounter, 'count', 1)
                            average_stat(player_this_encounter, 'success_percentage', 100 if encounter.success else 0)

                            get_and_add(player_this_archetype, 'count', 1)
                            get_and_add(player_this_profession, 'count', 1)

                            get_and_add(player_this_build, 'count', 1)
                            stats_in_phase_to_all = player_stats['Metrics']['damage']['To']['*All']
                            stats_in_phase_events = player_stats['Metrics']['events']

                            def calculate(l, f, *args):
                                for t in l:
                                    f(t, *args)

                            breakdown = [player_this_build,
                                        player_this_archetype,
                                        player_archetype_encounter,
                                        player_build_encounter]
                            all = breakdown + [player_summary]
                            if(encounter.success):
                                dps = stats_in_phase_to_all['dps']
                                dead_percentage = 100 * stats_in_phase_events['dead_time'] / duration
                                down_percentage = 100 * stats_in_phase_events['down_time'] / duration
                                disconnect_percentage = 100 * stats_in_phase_events['disconnect_time'] / duration

                                calculate(breakdown, all_stats, 'dps', dps)
                                calculate(all, average_stat, 'dead_percentage', dead_percentage)
                                calculate(all, average_stat, 'down_percentage', down_percentage)
                                average_stat(player_summary, 'disconnect_percentage', disconnect_percentage)

                            #else:
                                #init_bounds(player_this_build, 'dps')
                        except Exception as e:
                            print("Toeofdoom's amazing code threw an exception, well done.", e)

                    totals_in_area = get_or_create(totals['area'], encounter.area_id)

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

                    EraAreaStore.objects.update_or_create(
                            era=era, area_id=area_id, defaults={ "val": totals_in_area })

            # TODO remove if we ignore the unnecessary processing above (`if user_id:`)
            if None in totals['user']:
                del totals['user'][None]

            for user_id, totals_for_player in totals['user'].items():
                def finalise_stats(node):
                    try:
                        for key in list(node):
                            sections = str(key).split('|')
                            if sections[0] == 'avgsum':
                                node['avg_' + sections[1]] = node[key]/node['avgnum|' + sections[1]]
                                del node['avgsum|' + sections[1]]
                                del node['avgnum|' + sections[1]]
                            elif key in node:
                                finalise_stats(node[key])
                    except TypeError:
                        pass

                finalise_stats(totals_for_player)

                if options['verbosity'] >= 3:
                    # DEBUG
                    flattened = flatten(totals_for_player)
                    for key in sorted(flattened.keys()):
                        print_node(key, flattened[key])

                EraUserStore.objects.update_or_create(
                        era=era, user_id=user_id, defaults={ "val": totals_for_player })

            if options['verbosity'] >= 2:
                import pprint
                pp = pprint.PrettyPrinter(indent=2)
                print(era)
                pp.pprint(totals)


def is_basic_value(node):
    try:
        dict(node)
        return False
    except:
        return True

def flatten(root):
    nodes = dict((key, node) for key,node in root.items())
    stack = list(nodes.keys())
    for node_name in stack:
        node = nodes[node_name]
        try:
            for child_name, child in node.items():
                try:
                    full_child_name = "{0}-{1}".format(node_name, child_name)
                    nodes[full_child_name] = dict(child)
                    stack.append(full_child_name)
                except TypeError:
                    pass
                except ValueError:
                    pass
        except AttributeError:
            pass
    return nodes

def format_value(value):
    return value

def print_node(key, node, f=None):
    try:
        basic_values = list(filter(lambda key:is_basic_value(key[1]), node.items()))
        if basic_values:
            output_string = "{0}: {1}".format(key, ", ".join(
                ["{0}:{1}".format(name, format_value(value)) for name,value in basic_values]))
            print(output_string, file=f)
    except AttributeError:
        pass
