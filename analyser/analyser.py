from enum import IntEnum
from evtcparser import *
import pandas as pd
import numpy as np
from functools import reduce
from .collector import *

# DEBUG
from sys import exit
import timeit

class Group:
    CATEGORY = "Category"
    PLAYER = "Player"
    PHASE = "Phase"
    DESTINATION = "To"
    SKILL = "Skill"

class LogType(IntEnum):
    UNKNOWN = 0
    POWER = 1
    CONDI = 2
    APPLY = 3
    ACTIVATION = 4
    STATUSREMOVE = 5

class ContextType:
    DURATION = "Duration"
    TOTAL_DAMAGE_FROM_SOURCE_TO_DESTINATION = "Total Damage"
    TOTAL_DAMAGE_TO_DESTINATION = "Target Damage"
    SKILL_NAME = "Skill Name"
    AGENT_NAME = "Agent Name"
    PROFESSION_NAME = "Profession Name"

def per_second(f):
    return portion_of(f, ContextType.DURATION)

def assign_event_types(events):
    events['type'] = np.where(
        events['is_activation'] != parser.Activation.NONE, LogType.ACTIVATION,
            # non-activation events
            np.where(events['is_buffremove'] != 0, LogType.STATUSREMOVE,

            # non-statusremove events
            np.where(events['buff'] == 0, LogType.POWER,

            # buff events
            np.where(events['buff_dmg'] != 0, LogType.CONDI,
            LogType.APPLY))))

    #print(events.groupby('type').count())
    return events

class Boss:
    def __init__(self, name, profs, invuln=None):
        self.name = name
        self.profs = profs
        self.invuln = invuln

BOSS_ARRAY = [
    Boss('Vale Guardian', [0x3C4E], invuln=20000),
    Boss('Gorseval', [0x3C45], invuln=30000),
    Boss('Sabetha', [0x3C0F], invuln=25000),
    Boss('Slothasor', [0x3EFB], invuln=7000),
    Boss('Bandit Trio', [0x3ED8, 0x3F09, 0x3EFD]),
    Boss('Matthias', [0x3EF3]),
    Boss('Keep Construct', [0x3F6B]),
    Boss('Xera', [0x3F76, 0x3F9E], invuln=60000),
    Boss('Cairn', [0x432A]),
    Boss('Mursaat Overseer', [0x4314]),
    Boss('Samarog', [0x4324], invuln=20000),
    Boss('Deimos', [0x4302]),
]
BOSSES = {boss.profs[0]: boss for boss in BOSS_ARRAY}

def collect_individual_status(collector, player):
    only_entry = player.iloc[0]
    collector.add_data('profession', parser.AgentType(only_entry['prof']).name, str)
    collector.add_data('is_elite', only_entry['elite'], bool)
    collector.add_data('toughness', only_entry['toughness'], int)
    collector.add_data('healing', only_entry['healing'], int)
    collector.add_data('condition', only_entry['condition'], int)
    collector.add_data('archetype', only_entry['archetype'], str)
    collector.add_data('account', only_entry['account'], str)

def collect_player_status(collector, players):
    # player archetypes
    players = players.assign(archetype="Power")  # POWER
    players.loc[players.condition >= 7, 'archetype'] = "Condi"  # CONDI
    players.loc[players.toughness >= 7, 'archetype'] = "Tank"  # TANK
    players.loc[players.healing >= 7, 'archetype'] = "Heal"  # HEAL
    collector.group(collect_individual_status, players, ('name', 'Name'))

def collect_group_damage(collector, events):
    power_events = events[events.type == LogType.POWER]
    condi_events = events[events.type == LogType.CONDI]
    # print(events.columns)
    collector.add_data('power', power_events['damage'].sum(), int)
    collector.add_data('condi', condi_events['damage'].sum(), int)
    collector.add_data('total', events['damage'].sum(), int)

def collect_power_skill_data(collector, events):
    collector.add_data('fifty', events['is_fifty'].mean(), percentage)
    collector.add_data('scholar', events['is_ninety'].mean(), percentage)
    collector.add_data('seaweed', events['is_moving'].mean(), percentage)
    collector.add_data('total', events['damage'].sum(), int)
    collector.add_data('dps', events['damage'].sum(), per_second(int))
    collector.add_data('percentage', events['damage'].sum(),
                       percentage_of(ContextType.TOTAL_DAMAGE_FROM_SOURCE_TO_DESTINATION))

def collect_condi_skill_data(collector, events):
    collector.add_data('total', events['damage'].sum(), int)
    collector.add_data('dps', events['damage'].sum(), per_second(int))
    collector.add_data('percentage', events['damage'].sum(),
                       percentage_of(ContextType.TOTAL_DAMAGE_FROM_SOURCE_TO_DESTINATION))

def collect_individual_damage(collector, events):
    power_events = events[events.type == LogType.POWER]
    condi_events = events[events.type == LogType.CONDI]
    collector.set_context_value(ContextType.TOTAL_DAMAGE_FROM_SOURCE_TO_DESTINATION,
                                events['damage'].sum())
    # print(events.columns)
    collector.add_data('fifty', power_events['is_fifty'].mean(), percentage)
    collector.add_data('scholar', power_events['is_ninety'].mean(), percentage)
    collector.add_data('seaweed', power_events['is_moving'].mean(), percentage)
    collector.add_data('power', power_events['damage'].sum(), int)
    collector.add_data('condi', condi_events['damage'].sum(), int)
    collector.add_data('total', events['damage'].sum(), int)
    collector.add_data('power_dps', power_events['damage'].sum(), per_second(int))
    collector.add_data('condi_dps', condi_events['damage'].sum(), per_second(int))
    collector.add_data('dps', events['damage'].sum(), per_second(int))
    collector.add_data('percentage', events['damage'].sum(),
                       percentage_of(ContextType.TOTAL_DAMAGE_TO_DESTINATION))

    collector.group(collect_power_skill_data, power_events,
                    ('skillid', Group.SKILL, mapped_to(ContextType.SKILL_NAME)))
    collector.group(collect_condi_skill_data, condi_events,
                    ('skillid', Group.SKILL, mapped_to(ContextType.SKILL_NAME)))

def collect_destination_damage(collector, damage_events):
    collector.set_context_value(ContextType.TOTAL_DAMAGE_TO_DESTINATION,
                                damage_events['damage'].sum())
    collector.group(collect_group_damage, damage_events)
    collector.group(collect_individual_damage, damage_events,
                    ('ult_src_instid', Group.PLAYER, mapped_to(ContextType.AGENT_NAME)))

def collect_phase_damage(collector, damage_events):
    collector.set_context_value(
        ContextType.DURATION,
        float(damage_events['time'].max() - damage_events['time'].min())/1000.0)
    collector.group(collect_destination_damage, damage_events,
                    ('dst_instid', Group.DESTINATION, mapped_to(ContextType.AGENT_NAME)))
    collector.with_key(Group.DESTINATION, "*All").run(collect_destination_damage, damage_events)

def collect_damage(collector, player_events):
    player_events = assign_event_types(player_events)
    damage_events = player_events[(player_events.type == LogType.POWER)
                                  |(player_events.type == LogType.CONDI)]
    damage_events = damage_events.assign(
        damage = np.where(damage_events.type == LogType.POWER,
                          damage_events['value'], damage_events['buff_dmg']))

    collector.with_key(Group.PHASE, "All").run(collect_phase_damage, damage_events)

    phases = []
    for i in range(0,len(phases)):
        phase_events = damage_events
        collector.with_key(Group.PHASE, "Phase {0}".format(i)).run(collect_phase_damage, phase_events)

class Analyser:
    def __init__(self, encounter):
        boss = BOSSES[encounter.area_id]

        collector = Collector.root([Group.CATEGORY, Group.PHASE, Group.PLAYER, Group.DESTINATION, Group.SKILL])

        # ultimate source (e.g. if necro minion attacks, the necro himself)
        events = encounter.events
        agents = encounter.agents
        skills = encounter.skills

        skill_map = dict([(key, skills.loc[key, 'name']) for key in skills.index])
        agent_map = dict([(key, agents.loc[key, 'name']) for key in agents.index])
        collector.set_context_value(ContextType.SKILL_NAME, skill_map)
        collector.set_context_value(ContextType.AGENT_NAME, agent_map)

        events['ult_src_instid'] = events.src_master_instid.where(
            events.src_master_instid != 0, events.src_instid)
        players = agents[agents.party != 0]
        player_events = events[events.ult_src_instid.isin(players.index)].sort_values(by='time')

        collector.with_key(Group.CATEGORY, "status").run(collect_player_status, players)
        collector.with_key(Group.CATEGORY, "damage").run(collect_damage, player_events)

        start_event = events[events.state_change == parser.StateChange.LOG_START]
        start_timestamp = start_event['value'][0]
        start_time = start_event['time'][0]
        encounter_end = events.time.max()

        self.info = {
            'name': boss.name,
            'start': int(start_timestamp),
            'end': int(start_timestamp + int((encounter_end - start_time) / 1000)),
        }

        # saved as a JSON dump
        self.data = collector.all_data
