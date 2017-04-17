from enum import IntEnum
from evtcparser import *
import pandas as pd
import numpy as np
from functools import reduce
from .collector import *
from .buffs import *

# DEBUG
from sys import exit
import timeit

class Group:
    CATEGORY = "Category"
    PLAYER = "Player"
    PHASE = "Phase"
    DESTINATION = "To"
    SKILL = "Skill"
    SUBGROUP = "Subgroup"

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

class Elite(IntEnum):
    CORE = 0
    HEART_OF_THORNS = 1

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

def unique_names(dictionary):
    unique = dict()
    existing_names = set()
    for key in dictionary:
        base_name = dictionary[key]
        name = base_name
        index = 1
        while name in existing_names:
            index += 1
            name = "{0}-{1}".format(base_name, index)
        unique[key] = name
        existing_names.add(name)
    return unique

class Analyser:
    def __init__(self, encounter):
        boss = BOSSES[encounter.area_id]
        collector = Collector.root([Group.CATEGORY, Group.PHASE, Group.PLAYER, Group.DESTINATION, Group.SKILL])

        #set up data structures
        events = encounter.events
        agents = encounter.agents
        skills = encounter.skills
        players = agents[agents.party != 0]
        bosses = agents[agents.prof.isin(boss.profs)]

        events['ult_src_instid'] = events.src_master_instid.where(
            events.src_master_instid != 0, events.src_instid)
        events = assign_event_types(events)
        player_events = events[events.ult_src_instid.isin(players.index)].sort_values(by='time')

        #set up context
        skill_map = unique_names(dict([(key, skills.loc[key, 'name']) for key in skills.index]))
        agent_map = unique_names(dict([(key, agents.loc[key, 'name']) for key in agents.index]))
        collector.set_context_value(ContextType.SKILL_NAME, skill_map)
        collector.set_context_value(ContextType.AGENT_NAME, agent_map)

        #set up important preprocessed data
        self.subgroups = dict([(number, subgroup.index.values) for number, subgroup in players.groupby("party")])
        self.boss_instids = bosses.index.values

        #experimental phase calculations
        boss_events = events[events.dst_instid.isin(self.boss_instids)]
        boss_power_events = boss_events[(boss_events.type == LogType.POWER) & (boss_events.value > 0)]

        deltas = boss_power_events.time - boss_power_events.time.shift(1)
        boss_power_events = boss_power_events.assign(delta = deltas)
        phase_splits = boss_power_events[boss_power_events.delta > 10000]
        phase_starts = [events.time.min()] + list(phase_splits.time)
        phase_ends = list(phase_splits.time - phase_splits.delta) + [events.time.max()]
        print("Autodetected phases: {0} {1}".format(phase_starts, phase_ends))
        self.phases = list(zip(phase_starts, phase_ends))

        #time constraints
        start_event = events[events.state_change == parser.StateChange.LOG_START]
        start_timestamp = start_event['value'][0]
        start_time = start_event['time'][0]
        encounter_end = events.time.max()

        buff_data = BuffPreprocessor().process_events(start_time, encounter_end, skills, players, player_events)

        collector.with_key(Group.CATEGORY, "boss").run(self.collect_boss_status, bosses)
        collector.with_key(Group.CATEGORY, "boss").run(self.collect_boss_key_events, events)
        collector.with_key(Group.CATEGORY, "status").run(self.collect_player_status, players)
        collector.with_key(Group.CATEGORY, "damage").run(self.collect_damage, player_events)
        collector.with_key(Group.CATEGORY, "buffs").run(self.collect_player_buffs, buff_data)
        
        self.info = {
            'name': boss.name,
            'start': int(start_timestamp),
            'end': int(start_timestamp + int((encounter_end - start_time) / 1000)),
        }

        # saved as a JSON dump
        self.data = collector.all_data

    # Note: While this is just broken into areas with comments for now, we may want
    # a more concrete split in future

    # section: Agent stats (player/boss
    # subsection: boss stats
    def collect_invididual_boss_status(self, collector, boss):
        collector.add_data("Exists", True)

    def collect_boss_status(self, collector, bosses):
        collector.group(self.collect_invididual_boss_status, bosses, ('name', 'Name'))

    def collect_invididual_boss_key_events(self, collector, events):
        #all_state_changes = events[events.state_change != parser.StateChange.NORMAL]
        enter_combat_event = events[events.state_change == parser.StateChange.ENTER_COMBAT].iloc[0]
        death_event = events[events.state_change == parser.StateChange.CHANGE_DEAD].iloc[0]
        collector.add_data("EnterCombat", enter_combat_event.time)
        collector.add_data("Death", death_event.time)

    def collect_boss_key_events(self, collector, events):
        boss_events = events[events.ult_src_instid.isin(self.boss_instids)]
        collector.group(self.collect_invididual_boss_key_events, boss_events,
                        ('ult_src_instid', 'Name', mapped_to(ContextType.AGENT_NAME)))

    #subsection: player stats
    def collect_player_status(self, collector, players):
        # player archetypes
        players = players.assign(archetype=Archetype.POWER)
        players.loc[players.condition >= 7, 'archetype'] = Archetype.CONDI
        players.loc[players.toughness >= 7, 'archetype'] = Archetype.TANK
        players.loc[players.healing >= 7, 'archetype'] = Archetype.HEAL
        collector.group(self.collect_individual_status, players, ('name', 'Name'))

    def collect_individual_status(self, collector, player):
        only_entry = player.iloc[0]
        # collector.add_data('profession_name', parser.AgentType(only_entry['prof']).name, str)
        collector.add_data('profession', only_entry['prof'], parser.AgentType)
        collector.add_data('elite', only_entry['elite'], Elite)
        collector.add_data('toughness', only_entry['toughness'], int)
        collector.add_data('healing', only_entry['healing'], int)
        collector.add_data('condition', only_entry['condition'], int)
        collector.add_data('archetype', only_entry['archetype'], Archetype)
        collector.add_data('party', only_entry['party'], int)
        collector.add_data('account', only_entry['account'], str)


    #section: Damage stats
    #subsection: Filtering events
    def collect_damage(self, collector, player_events):
        #prepare damage_events
        damage_events = player_events[(player_events.type == LogType.POWER)
                                      |(player_events.type == LogType.CONDI)]
        damage_events = damage_events.assign(
            damage = np.where(damage_events.type == LogType.POWER,
                              damage_events['value'], damage_events['buff_dmg']))
        damage_events = damage_events[damage_events.damage > 0]

        #determine phases
        collector.with_key(Group.PHASE, "All").run(self.collect_phase_damage, damage_events)
        for i in range(0,len(self.phases)):
            phase = self.phases[i]
            phase_events = damage_events[(damage_events.time >= phase[0]) & (damage_events.time <= phase[1])]
            collector.with_key(Group.PHASE, "{0}".format(i+1)).run(self.collect_phase_damage, phase_events)

    def collect_phase_damage(self, collector, damage_events):
        collector.set_context_value(
            ContextType.DURATION,
            float(damage_events['time'].max() - damage_events['time'].min())/1000.0)

        boss_events = damage_events[damage_events.dst_instid.isin(self.boss_instids)]
        add_events = damage_events[damage_events.dst_instid.isin(self.boss_instids) != True]

        collector.with_key(Group.DESTINATION, "*All").run(self.collect_destination_damage_with_skill_data, damage_events)
        collector.with_key(Group.DESTINATION, "*Boss").run(self.collect_destination_damage, boss_events)
        collector.with_key(Group.DESTINATION, "*Adds").run(self.collect_destination_damage, add_events)
        if len(self.boss_instids) > 1:
             collector.group(self.collect_destination_damage, boss_events,
                ('dst_instid', Group.DESTINATION, mapped_to(ContextType.AGENT_NAME)))

    def collect_destination_damage(self, collector, damage_events):
        collector.set_context_value(ContextType.TOTAL_DAMAGE_TO_DESTINATION,
                                    damage_events['damage'].sum())
        collector.run(self.collect_group_damage, damage_events)
        for subgroup in self.subgroups:
            subgroup_players = self.subgroups[subgroup]
            subgroup_events = damage_events[damage_events.ult_src_instid.isin(subgroup_players)]
            collector.with_key(Group.SUBGROUP, "{0}".format(subgroup)).run(
                self.collect_group_damage, subgroup_events)

        collector.group(self.collect_individual_damage, damage_events,
                        ('ult_src_instid', Group.PLAYER, mapped_to(ContextType.AGENT_NAME)))

    def collect_destination_damage_with_skill_data(self, collector, damage_events):
        self.collect_destination_damage(collector, damage_events)
        collector.group(self.collect_player_skill_damage, damage_events,
                        ('ult_src_instid', Group.PLAYER, mapped_to(ContextType.AGENT_NAME)))

    #subsection: Aggregating damage
    def collect_group_damage(self, collector, events):
        power_events = events[events.type == LogType.POWER]
        condi_events = events[events.type == LogType.CONDI]
        # print(events.columns)
        collector.add_data('scholar', power_events['is_ninety'].mean(), percentage)
        collector.add_data('seaweed', power_events['is_moving'].mean(), percentage)
        collector.add_data('power', power_events['damage'].sum(), int)
        collector.add_data('condi', condi_events['damage'].sum(), int)
        collector.add_data('total', events['damage'].sum(), int)
        collector.add_data('dps', events['damage'].sum(), per_second(int))
        collector.add_data('power_dps', power_events['damage'].sum(), per_second(int))
        collector.add_data('condi_dps', condi_events['damage'].sum(), per_second(int))

    def collect_individual_damage(self, collector, events):
        power_events = events[events.type == LogType.POWER]
        condi_events = events[events.type == LogType.CONDI]

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

    # subsection: detailed skill data
    def collect_player_skill_damage(self, collector, events):
        power_events = events[events.type == LogType.POWER]
        condi_events = events[events.type == LogType.CONDI]
        collector.set_context_value(ContextType.TOTAL_DAMAGE_FROM_SOURCE_TO_DESTINATION,
                                    events['damage'].sum())
        collector.group(self.collect_power_skill_data, power_events,
                        ('skillid', Group.SKILL, mapped_to(ContextType.SKILL_NAME)))
        collector.group(self.collect_condi_skill_data, condi_events,
                        ('skillid', Group.SKILL, mapped_to(ContextType.SKILL_NAME)))

    def collect_power_skill_data(self, collector, events):
        collector.add_data('fifty', events['is_fifty'].mean(), percentage)
        collector.add_data('scholar', events['is_ninety'].mean(), percentage)
        collector.add_data('seaweed', events['is_moving'].mean(), percentage)
        collector.add_data('total', events['damage'].sum(), int)
        collector.add_data('dps', events['damage'].sum(), per_second(int))
        collector.add_data('percentage', events['damage'].sum(),
                           percentage_of(ContextType.TOTAL_DAMAGE_FROM_SOURCE_TO_DESTINATION))

    def collect_condi_skill_data(self, collector, events):
        collector.add_data('total', events['damage'].sum(), int)
        collector.add_data('dps', events['damage'].sum(), per_second(int))
        collector.add_data('percentage', events['damage'].sum(),
                           percentage_of(ContextType.TOTAL_DAMAGE_FROM_SOURCE_TO_DESTINATION))

    #Section: buff stats
    def collect_player_buffs(self, collector, buff_data):
        collector.with_key(Group.PHASE, "All").run(self.collect_all_player_buffs, buff_data);

    def collect_all_player_buffs(self, collector, buff_data):
        collector.group(self.collect_individual_player_buffs, buff_data,
                        ('player', Group.PLAYER, mapped_to(ContextType.AGENT_NAME)))

    def collect_individual_player_buffs(self, collector, buff_data):
        for buff_type in BUFF_TYPES:
            buff_specific_data = buff_data[buff_data['buff'] == buff_type.code];
            diff_data = (buff_specific_data[['time']].diff(periods=-1, axis=0)[:-1] * -1).join(buff_specific_data[['stacks']])
            mean = (diff_data['time'] * diff_data['stacks']).sum() / diff_data['time'].sum()
            if buff_type.stacking == StackType.INTENSITY:
                collector.add_data(buff_type.code, mean)
            else:
                collector.add_data(buff_type.code, mean, percentage)

