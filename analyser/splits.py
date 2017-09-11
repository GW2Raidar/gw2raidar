from enum import IntEnum
from evtcparser import *
import pandas as pd
import numpy as np
from functools import reduce
from .collector import *

class Group:
    CATEGORY = "Category"
    PLAYER = "Player"
    BOSS = "Boss"
    PHASE = "Phase"
    DESTINATION = "To"
    SOURCE = "From"
    SKILL = "Skill"
    SUBGROUP = "Subgroup"
    BUFF = "Buff"
    METRICS = "Metrics"
    
class ContextType:
    DURATION = "Duration"
    TOTAL_DAMAGE_FROM_SOURCE_TO_DESTINATION = "Total Damage"
    TOTAL_DAMAGE_TO_DESTINATION = "Target Damage"
    SKILL_NAME = "Skill Name"
    AGENT_NAME = "Agent Name"
    PROFESSION_NAME = "Profession Name"
    BUFF_TYPE = "Buff"

def split_duration_event_by_phase(collector, method, events, phases):
    def collect_phase(name, phase_events):
        duration = float(phase_events['time'].max() - phase_events['time'].min())/1000.0
        if not duration > 0.001:
            duration = 0
        collector.set_context_value(ContextType.DURATION, duration)
        collector.with_key(Group.PHASE, name).run(method, phase_events)

    collect_phase("All", events)

    #Yes, this lists each phase individually even if there is only one
    #That's for consistency for things like:
    #Some things happen outside a phase.
    #Some fights have multiple phases, but you only get to phase one
    #Still want to list it as phase 1
    for i in range(0,len(phases)):
        phase = phases[i]
        start = phase[1]
        end = phase[2]

        if len(events) > 0:
            across_phase = events[(events['time'] < start) & (events['time'] + events['duration'] > end)]

            #HACK: review why copy?
            before_phase = events[(events['time'] < start) & (events['time'] + events['duration'] > start) & (events['time'] + events['duration'] <= end)].copy()
            main_phase = events[(events['time'] >= start) & (events['time'] + events['duration'] <= end)]
            after_phase = events[(events['time'] >= start) & (events['time'] < end) & (events['time'] + events['duration'] > end)]

            across_phase = across_phase.assign(time = start, duration = end - start)

            before_phase.loc[:, 'duration'] = before_phase['duration'] + before_phase['time'] - start
            before_phase = before_phase.assign(time = start)

            after_phase = after_phase.assign(duration = end)
            after_phase.loc[:, 'duration'] = after_phase['duration'] - after_phase['time']

            collect_phase(phase[0], across_phase.append(before_phase).append(main_phase).append(after_phase))
        else:
            collect_phase(phase[0], events)
                
def split_by_phase(collector, method, events, phases):
    def collect_phase(name, phase_events, duration):
        #duration = float(phase_events['time'].max() - phase_events['time'].min())/1000.0
        if not duration > 0.001:
            duration = 0
        collector.set_context_value(ContextType.DURATION, duration)
        collector.with_key(Group.PHASE, name).run(method, phase_events)

    collect_phase("All", events)

    #Yes, this lists each phase individually even if there is only one
    #That's for consistency for things like:
    #Some things happen outside a phase.
    #Some fights have multiple phases, but you only get to phase one
    #Still want to list it as phase 1
    for i in range(0,len(phases)):
        phase = phases[i]
        phase_events = events[(events.time >= phase[1]) & (events.time <= phase[2])]
        collect_phase(phase[0], phase_events, phase[2] - phase[1])

def split_by_player_groups(collector, method, events, player_column, subgroups, players):
    collector.with_key(Group.SUBGROUP, "*All").run(method, events)
    for subgroup in subgroups:
        subgroup_players = subgroups[subgroup]
        subgroup_events = events[events[player_column].isin(subgroup_players)]
        collector.with_key(Group.SUBGROUP, "{0}".format(subgroup)).run(
            method, subgroup_events)
    split_by_player(collector, method, events, player_column, players)

def split_by_player(collector, method, events, player_column, players):
    for character in players.groupby('name').groups.items():
        characters = players[players['name'] == character[0]]
        collector.with_key(Group.PLAYER, character[0]).run(method,events[events[player_column].isin(characters.index)]) 

def split_by_agent(collector, method, events, group, enemy_column, bosses, players):
    boss_events = events[events[enemy_column].isin(bosses)]
    player_events = events[events[enemy_column].isin(players)]

    non_add_instids = bosses
    add_events = events[events[enemy_column].isin(non_add_instids) != True]

    collector.with_key(group, "*All").run(method, events)
    collector.with_key(group, "*Boss").run(method, boss_events)
    collector.with_key(group, "*Players").run(method, player_events)
    collector.with_key(group, "*Adds").run(method, add_events)
    if len(bosses) > 1:
        split_by_boss(collector, method, boss_events, enemy_column, group)

def split_by_boss(collector, method, events, enemy_column, group):
    collector.group(method, events,
            (enemy_column, group, mapped_to(ContextType.AGENT_NAME)))

def split_by_skill(collector, method, events):
    collector.group(method, events,
                    ('skillid', Group.SKILL, mapped_to(ContextType.SKILL_NAME)))