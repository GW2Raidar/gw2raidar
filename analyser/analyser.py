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

class Archetype(IntEnum):
    POWER = 0
    HEAL = 1
    CONDI = 2
    TANK = 3

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

class StackType(IntEnum):
    INTENSITY = 0
    DURATION = 1

class BuffType:
    def __init__(self, name, code, stacking, capacity):
        self.name = name
        self.code = code
        self.stacking = stacking
        self.capacity = capacity

BUFF_TYPES = [
        # General Boons
        BuffType('Might', 'might', StackType.INTENSITY, 25),
        BuffType('Quickness', 'quickness', StackType.DURATION, 5),
        BuffType('Fury', 'fury', StackType.DURATION, 9),
        BuffType('Protection', 'protection', StackType.DURATION, 5),
        BuffType('Alacrity', 'alacrity', StackType.DURATION, 9),

        # Ranger
        BuffType('Spotter', 'spotter', StackType.DURATION, 1),
        BuffType('Spirit of Frost', 'spirit_of_frost', StackType.DURATION, 1),
        BuffType('Sun Spirit', 'sun_spirit', StackType.DURATION, 1),
        BuffType('Stone Spirit', 'stone_spirit', StackType.DURATION, 1),
        BuffType('Storm Spirit', 'storm_spirit', StackType.DURATION, 1),
        BuffType('Glyph of Empowerment', 'glyph_of_empowerment', StackType.DURATION, 1),
        BuffType('Grace of the Land', 'gotl', StackType.INTENSITY, 5),

        # Warrior
        BuffType('Empower Allies', 'empower_allies', StackType.DURATION, 1),
        BuffType('Banner of Strength', 'banner_strength', StackType.DURATION, 1),
        BuffType('Banner of Discipline', 'banner_discipline', StackType.DURATION, 1),
        BuffType('Banner of Tactics', 'banner_tactics', StackType.DURATION, 1),
        BuffType('Banner of Defence', 'banner_defence', StackType.DURATION, 1),

        # Revenant
        BuffType('Assassin''s Presence', 'assassins_presence', StackType.DURATION, 1),
        BuffType('Naturalistic Resonance', 'naturalistic_resonance', StackType.DURATION, 1),

        # Engineer
        BuffType('Pinpoint Distribution', 'pinpoint_distribution', StackType.DURATION, 1),

        # Elementalist
        BuffType('Soothing Mist', 'soothing_mist', StackType.DURATION, 1),

        # Necro
        BuffType('Vampiric Presence', 'vampiric_presence', StackType.DURATION, 1)
    ]

BUFFS = { buff.name: buff for buff in BUFF_TYPES }

class BuffTrackIntensity:
    def __init__(self, buff_type, encounter_start, encounter_end):
        self.buff_type = buff_type;
        self.stack_end_times = []
        self.start_time = encounter_start
        self.data = np.array([np.arange(1)] * 2).T
        self.current_time = 0

    def add_event(self, event):
        event_time = int(event.time - self.start_time);
        if event_time != self.current_time:
            self.simulate_to_time(event_time)

        if len(self.stack_end_times) < self.buff_type.capacity:
            self.stack_end_times += [event_time + event.value]
            self.stack_end_times.sort()
            if self.data[-1][0] == event_time:
                self.data[-1][1] = len(self.stack_end_times);
            else:
                self.data = np.append(self.data, [[event_time, len(self.stack_end_times)]], axis=0)
        elif (self.stack_end_times[0] < event_time + event.value):
            self.stack_end_times[0] = event_time + event.value
            self.stack_end_times.sort()

    def simulate_to_time(self, new_time):
        while len(self.stack_end_times) > 0 and self.stack_end_times[0] <= new_time:
            if self.data[-1][0] == self.stack_end_times[0]:
                self.data[-1][1] = len(self.stack_end_times) - 1
            else:
                self.data = np.append(self.data, [[int(self.stack_end_times[0]), len(self.stack_end_times) - 1]], axis=0)
            self.stack_end_times.remove(self.stack_end_times[0])
        self.current_time = new_time

    def end_track(self, time):
        end_time = int(time - self.start_time);
        self.simulate_to_time(end_time)
        if self.data[-1][0] != end_time:
            self.data = np.append(self.data, [[end_time, len(self.stack_end_times)]], axis=0)

class BuffTrackDuration:
    def __init__(self, buff_type, encounter_start, encounter_end):
        self.buff_type = buff_type;
        self.stack_durations = np.array([np.arange(0)]).T
        self.start_time = encounter_start
        self.data = np.array([np.arange(1)] * 2).T
        self.current_time = 0

    def add_event(self, event):
        event_time = int(event.time - self.start_time);
        if event_time != self.current_time:
            self.simulate(event_time - self.current_time)

        if self.stack_durations.size < self.buff_type.capacity:
            if self.stack_durations.size == 0:
                if self.data[-1][0] == event_time:
                    self.data[-1][1] = 1;
                else:
                    self.data = np.append(self.data, [[event_time, 1]], axis=0)
            self.stack_durations = np.append(self.stack_durations, [event.value])
            self.stack_durations.sort()
        elif (self.stack_durations[0] < event.value):
            self.stack_durations[0] = event.value
            self.stack_durations.sort()

    def simulate(self, delta_time):
        remaining_delta = delta_time
        while self.stack_durations.size > 0 and self.stack_durations[0] <= remaining_delta:
            if self.stack_durations.size == 1:
                if self.data[-1][0] == self.stack_durations[0] + self.current_time:
                    self.data[-1][1] = 0
                else:
                    self.data = np.append(self.data, [[int(self.stack_durations[0] + self.current_time), 0]], axis=0)
            remaining_delta -= self.stack_durations[0]
            self.stack_durations = np.delete(self.stack_durations, 0)

        self.current_time += delta_time
        if self.stack_durations.size > 0:
            self.stack_durations[0] -= remaining_delta

    def end_track(self, time):
        end_time = int(time - self.start_time);
        self.simulate(end_time - self.current_time)
        if self.data[-1][0] != end_time:
            self.data = np.append(self.data, [[end_time, self.stack_durations.size > 0]], axis=0)

def collect_individual_status(collector, player):
    only_entry = player.iloc[0]
    # collector.add_data('profession_name', parser.AgentType(only_entry['prof']).name, str)
    collector.add_data('profession', only_entry['prof'], int)
    collector.add_data('elite', only_entry['elite'], int)
    collector.add_data('toughness', only_entry['toughness'], int)
    collector.add_data('healing', only_entry['healing'], int)
    collector.add_data('condition', only_entry['condition'], int)
    collector.add_data('archetype', only_entry['archetype'], int)
    collector.add_data('party', only_entry['party'], int)
    collector.add_data('account', only_entry['account'], str)

def collect_player_status(collector, players):
    # player archetypes
    players = players.assign(archetype=Archetype.POWER)
    players.loc[players.condition >= 7, 'archetype'] = Archetype.CONDI
    players.loc[players.toughness >= 7, 'archetype'] = Archetype.TANK
    players.loc[players.healing >= 7, 'archetype'] = Archetype.HEAL
    collector.group(collect_individual_status, players, ('name', 'Name'))

def collect_group_damage(collector, events):
    power_events = events[events.type == LogType.POWER]
    condi_events = events[events.type == LogType.CONDI]
    # print(events.columns)
    collector.add_data('power', power_events['damage'].sum(), int)
    collector.add_data('condi', condi_events['damage'].sum(), int)
    collector.add_data('total', events['damage'].sum(), int)
    # XXX is this correct?
    collector.add_data('fifty', events['is_fifty'].mean(), percentage)
    collector.add_data('scholar', events['is_ninety'].mean(), percentage)
    collector.add_data('seaweed', events['is_moving'].mean(), percentage)
    collector.add_data('dps', events['damage'].sum(), per_second(int))

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
