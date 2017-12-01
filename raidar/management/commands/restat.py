from ._qsetiter import queryset_iterator
from collections import defaultdict
from functools import partial
from contextlib import contextmanager
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.utils import IntegrityError
from gw2raidar import settings
from analyser.bosses import BOSSES, Kind
from os.path import join as path_join
from raidar.models import *
from sys import exit
from time import time
import os
import csv
from evtcparser.parser import AgentType
import pandas as pd
import numpy as np
import base64
# XXX DEBUG
# import logging
# l = logging.getLogger('django.db.backends')
# l.setLevel(logging.DEBUG)
# l.addHandler(logging.StreamHandler())



@contextmanager
def single_process(name):
    try:
        pid = os.getpid()
        #Uncomment to remove pid in case of having cancelled restat with Ctrl+C...
        #Variable.objects.get(key='%s_pid' % name).delete()
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

def name_for(id):
    if id in BOSSES:
        return BOSSES[id].name
    return AgentType(id).name


def navigate(node, *names):
    new_node = node
    for name in names:
        if name not in new_node:
            new_node[name] = dict()
        new_node = new_node[name]
    return new_node

#Automated statistics style:
def count(output):
    current = output.get('count', 0)
    output['count'] = current+ 1

def bound_stats(output, name, value):
    maxprop = 'max_' + name
    if maxprop not in output or value > output[maxprop]:
        output[maxprop] = value

    minprop = 'min_' + name
    if minprop not in output or value < output[minprop]:
        output[minprop] = value

def advanced_stats(maximum_percentile_samples, output, name, value):
    bound_stats(output, name, value)
    average_stats(output, name, value)
    l = output.get('values|' + name, [])
    if(len(l) < maximum_percentile_samples):
        l.append(value)
        output['values|' + name] = l

def all_stats(output, name, value):
    bound_stats(output, name, value)
    average_stats(output, name, value)

def average_stats(output, name, value):
    output['avgsum|' + name] = output.get('avgsum|' + name, 0) + value
    output['avgnum|' + name] = output.get('avgnum|' + name, 0) + 1

def finalise_stats(node):
    try:
        for key in list(node):
            sections = str(key).split('|')
            if sections[0] == 'avgsum':
                node['avg_' + sections[1]] = node[key]/node['avgnum|' + sections[1]]
                del node['avgsum|' + sections[1]]
                del node['avgnum|' + sections[1]]
            if sections[0] == 'values':
                values = node[key]
                """def percentile(n):
                    i, p = divmod((len(values)-1) * n, 100)
                    n = values[i]
                    if(p > 0):
                        n = ((n * (100-p)) + (values[i+1] * p))/100
                    return n"""
                #node['n_' + sections[1]] = len(values)
                b = np.percentile(values, q = range(0,100)).astype(np.float32).tobytes()
                node['per_' + sections[1]] = base64.b64encode(b).decode('utf-8')
                #node['per_a_' + sections[1]] = np.frombuffer(b, np.float32).tolist()
                del node['values|' + sections[1]]
            elif key in node:
                finalise_stats(node[key])
    except TypeError:
        pass

def _safe_get(func, default=0):
    try:
        return func()
    except (KeyError, TypeError):
        return default

#subprocesses
def calculate(l, f, *args):
    for t in l:
        f(t, *args)

def calculate_standard_stats(f, stats, main_stat_targets, incoming_buff_targets, outgoing_buff_targets):
    stats_in_phase_to_all = _safe_get(lambda: stats['Metrics']['damage']['To']['*All'], {})
    stats_in_phase_to_boss = _safe_get(lambda: stats['Metrics']['damage']['To']['*Boss'], {})
    stats_in_phase_from_all = _safe_get(lambda: stats['Metrics']['damage']['From']['*All'], {})
    shielded_in_phase_from_all = _safe_get(lambda: stats['Metrics']['shielded']['From']['*All'], {})
    outgoing_buff_stats = _safe_get(lambda: stats['Metrics']['buffs']['To']['*All'], {})
    incoming_buff_stats = _safe_get(lambda: stats['Metrics']['buffs']['From']['*All'], {})

    for stat in ['dps','crit','seaweed','scholar','flanking']:
        calculate(main_stat_targets, f, stat, stats_in_phase_to_all.get(stat, 0))
    calculate(main_stat_targets, f, 'dps_boss', stats_in_phase_to_boss.get('dps', 0))
    calculate(main_stat_targets, f, 'dps_received', stats_in_phase_from_all.get('dps', 0))
    calculate(main_stat_targets, f, 'total_received', stats_in_phase_from_all.get('total', 0))

    for buff, value in incoming_buff_stats.items():
        calculate(incoming_buff_targets, f, buff, value)

    for buff, value in outgoing_buff_stats.items():
        calculate(outgoing_buff_targets, f, buff, value)

def navigate_to_profile_outputs(totals, participation, encounter, boss):
    class ProfileOutputs:
        def __init__(self, breakdown, all, encounter_stats):
            self.breakdown = breakdown
            self.all = all
            self.encounter_stats = encounter_stats

    def categorise(split_encounter, split_archetype, split_profession):
            return navigate(totals_for_player,
                            'encounter', encounter.area_id if split_encounter else 'All %s bosses' % boss.kind.name.lower(),
                            'archetype', participation.archetype if split_archetype else 'All',
                            'profession', participation.character.profession if split_profession else 'All',
                            'elite', participation.elite if split_profession else 'All')

    user_id = participation.character.account.user_id

    if not user_id:
        return ProfileOutputs([],[],[])
    # TODO if user_id: # (otherwise we're ignoring the person)
    totals_for_player = navigate(totals['user'], user_id)
    #TODO: Remove if the one in player_summary is enough!
    count(totals_for_player)
    #profile categorisations
    player_summary = navigate(totals_for_player, 'summary')
    player_this_encounter = categorise(True, False, False)
    player_this_archetype = categorise(False, True, False)
    player_this_profession = categorise(False, False, True)
    player_this_build = categorise(False, True, True)
    player_archetype_encounter = categorise(True, True, False)
    player_build_encounter = categorise(True, True, True)
    player_profession_encounter = categorise(True, False, True)
    player_all = categorise(False, False, False)

    breakdown = [player_this_build,
                player_this_archetype,
                player_this_profession,
                player_archetype_encounter,
                player_build_encounter,
                player_profession_encounter]
    all = breakdown + [player_summary, player_this_encounter, player_all]
    encounter_stats = [player_this_encounter,
                       player_archetype_encounter,
                       player_build_encounter,
                       player_profession_encounter,
                       player_all]
    return ProfileOutputs(breakdown, all, encounter_stats)

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
        with single_process('restat'), necessary(options['force']) as last_run:
            start = time()
            self.delete_old_files(*args, **options)
            self.calculate_stats(*args, **options)
            end = time()

            if options['verbosity'] >= 3:
                print()
                print("Completed in %ss" % (end - start))


    def delete_old_files(self, *args, **options):
        GB = 1024 * 1024 * 1024
        MIN_DISK_AVAIL = 10 * GB

        def is_there_space_now():
            fsdata = os.statvfs(settings.UPLOAD_DIR)
            diskavail = fsdata.f_frsize * fsdata.f_bavail
            return diskavail > MIN_DISK_AVAIL

        if is_there_space_now():
            return

        encounter_queryset = Encounter.objects.filter(has_evtc=True).order_by('started_at')
        for encounter in queryset_iterator(encounter_queryset):
            filename = encounter.diskname()
            try:
                os.unlink(filename)
            except FileNotFoundError:
                pass
            encounter.has_evtc = False
            encounter.save()
            if is_there_space_now():
                return


    def calculate_stats(self, *args, **options):
        for era in Era.objects.all():
            # TODO: don't recalculate eras with no uploads
            totals = {
                "area": {},
                "user": {}
            }
            era_queryset = era.encounters.prefetch_related('participations__character', 'participations__character__account').all().order_by('?')
            totals_in_era = {}
            for encounter in queryset_iterator(era_queryset):
                boss = BOSSES[encounter.area_id]
                try:
                    data = encounter.val
                    duration = data['Category']['encounter']['duration'] * 1000
                    phases = data['Category']['combat']['Phase']
                    totals_in_area = navigate(totals['area'], encounter.area_id)

                    participations = encounter.participations.all()
                    for phase, stats_in_phase in phases.items():
                        squad_stats = stats_in_phase['Subgroup']['*All']
                        phase_duration = data['Category']['encounter']['duration'] if phase == 'All' else _safe_get(lambda: data['Category']['encounter']['Phase'][phase]['duration'])
                        group_totals = navigate(totals_in_area, phase, 'group')
                        buffs_by_party = navigate(group_totals, 'buffs')
                        buffs_out_by_party = navigate(group_totals, 'buffs_out')

                        group_totals_era = navigate(totals_in_era, phase, 'group')
                        buffs_by_party_era = navigate(group_totals_era, 'buffs')
                        buffs_out_by_party_era = navigate(group_totals_era, 'buffs_out')


                        if(encounter.success):
                            calculate([group_totals, group_totals_era],
                                      partial(advanced_stats, options['percentile_samples']),
                                      'duration',
                                      phase_duration)
                            calculate([group_totals, group_totals_era], count)
                            calculate_standard_stats(
                                partial(advanced_stats, options['percentile_samples']),
                                squad_stats,
                                [group_totals, group_totals_era],
                                [buffs_by_party, buffs_by_party_era],
                                [buffs_out_by_party, buffs_out_by_party_era])

                        individual_totals = navigate(totals_in_area, phase, 'individual')
                        individual_totals_era = navigate(totals_in_era, phase, 'individual')
                        for participation in participations:
                            # XXX in case player did not actually participate (hopefully fix in analyser)
                            if (participation.character.name not in stats_in_phase['Player']):
                                continue
                            player_stats = stats_in_phase['Player'][participation.character.name]

                            prof = participation.character.profession
                            arch = participation.archetype
                            elite = participation.elite
                            totals_by_build = navigate(totals_in_area, phase, 'build', prof, elite, arch)
                            totals_by_archetype = navigate(totals_in_area, phase, 'build', 'All', 'All', arch)
                            totals_by_spec = navigate(totals_in_area, phase, 'build', prof, elite, 'All')
                            buffs_by_build = navigate(totals_by_build, 'buffs')
                            buffs_out_by_build = navigate(totals_by_build, 'buffs_out')

                            #todo: add these only if in phase "all"
                            totals_by_build_era = navigate(totals_in_era, phase, 'build', prof, elite, arch)
                            totals_by_archetype_era = navigate(totals_in_era, phase, 'build', 'All', 'All', arch)
                            totals_by_spec_era = navigate(totals_in_era, phase, 'build', prof, elite, 'All')
                            buffs_by_build_era = navigate(totals_by_build_era, 'buffs')
                            buffs_out_by_build_era = navigate(totals_by_build_era, 'buffs_out')

                            if(encounter.success):
                                calculate([totals_by_build, totals_by_archetype, totals_by_spec, individual_totals,
                                     totals_by_build_era, totals_by_archetype_era, totals_by_spec_era, individual_totals_era], count)
                                calculate_standard_stats(
                                    partial(advanced_stats, options['percentile_samples']),
                                    player_stats,
                                    [totals_by_build, totals_by_archetype, totals_by_spec, individual_totals,
                                     totals_by_build_era, totals_by_archetype_era, totals_by_spec_era, individual_totals_era],
                                    [buffs_by_build, buffs_by_build_era],
                                    [buffs_out_by_build, buffs_out_by_build_era])

                            if phase == 'All':
                                profile_output = navigate_to_profile_outputs(totals, participation, encounter, boss)
                                stats_in_phase_events = _safe_get(lambda: player_stats['Metrics']['events'], None)
                                if stats_in_phase_events is not None:


                                    calculate(profile_output.all, count)
                                    calculate(profile_output.encounter_stats, average_stats, 'success_percentage', 100 if encounter.success else 0)

                                    if(encounter.success):
                                        calculate_standard_stats(
                                            all_stats,
                                            player_stats,
                                            profile_output.breakdown,
                                            [],
                                            [navigate(a, 'outgoing') for a in profile_output.breakdown])

                                        dead_percentage = 100 * stats_in_phase_events.get('dead_time', 0) / duration
                                        down_percentage = 100 * stats_in_phase_events.get('down_time', 0) / duration
                                        disconnect_percentage = 100 * stats_in_phase_events.get('disconnect_time', 0) / duration

                                        calculate(profile_output.all, average_stats, 'dead_percentage', dead_percentage)
                                        calculate(profile_output.all, average_stats, 'down_percentage', down_percentage)
                                        calculate(profile_output.all, average_stats, 'disconnect_percentage', disconnect_percentage)
                except:
                    raise RestatException("Error in %s" % encounter)

            #postprocessing
            for area_id, totals_in_area in totals['area'].items():
                finalise_stats(totals_in_area)
                EraAreaStore.objects.update_or_create(
                        era=era, area_id=area_id, defaults={ "val": totals_in_area })

            for user_id, totals_for_player in totals['user'].items():
                finalise_stats(totals_for_player)
                EraUserStore.objects.update_or_create(
                        era=era, user_id=user_id, defaults={ "val": totals_for_player })

            finalise_stats(totals_in_era)
            era.val=totals_in_era
            #Era.objects.update_or_create(era)
            era.save()

            if options['verbosity'] >= 2:
                flattened = flatten(totals)
                for key in sorted(flattened.keys()):
                    print_node(key, flattened[key])

            if options['verbosity'] >= 3:
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
    nodes = dict((str(key), node) for key,node in root.items())
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
