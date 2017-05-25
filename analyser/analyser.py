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
    BOSS = "Boss"
    PHASE = "Phase"
    DESTINATION = "To"
    SOURCE = "From"
    SKILL = "Skill"
    SUBGROUP = "Subgroup"
    BUFF = "Buff"

class LogType(IntEnum):
    UNKNOWN = 0
    POWER = 1
    CONDI = 2
    APPLY = 3
    ACTIVATION = 4
    STATUSREMOVE = 5

class Archetype(IntEnum):
    POWER = 1
    CONDI = 2
    TANK = 3
    HEAL = 4

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
    BUFF_TYPE = "Buff"

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

class EvtcAnalysisException(BaseException):
    pass

def only_entry(frame):
    return frame.iloc[0] if not frame.empty else None

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

def create_mapping(df, column):
    return unique_names(df.to_dict()[column])

def filter_damage_events(events):
    damage_events = events[(events.type == LogType.POWER) |(events.type == LogType.CONDI)]
    damage_events = damage_events.assign(damage =
                                         np.where(damage_events.type == LogType.POWER,
                                                  damage_events['value'],
                                                  damage_events['buff_dmg']))
    return damage_events[damage_events.damage > 0]

class Analyser:
    def preprocess_agents(self, agents, collector):
        players = agents[agents.party != 0]
        bosses = agents[agents.prof.isin(self.boss_info.profs)]
        final_bosses = agents[agents.prof == self.boss_info.profs[-1]]

        #set up important preprocessed data
        self.subgroups = dict([(number, subgroup.index.values) for number, subgroup in players.groupby("party")])
        self.player_instids = players.index.values
        self.boss_instids = bosses.index.values
        self.final_boss_instids = final_bosses.index.values
        collector.set_context_value(ContextType.AGENT_NAME, create_mapping(agents, 'name'))
        return players, bosses, final_bosses

    def preprocess_events(self, events):
        #experimental phase calculations
        events['ult_src_instid'] = events.src_master_instid.where(
            events.src_master_instid != 0, events.src_instid)
        events = assign_event_types(events)
        player_src_events = events[events.ult_src_instid.isin(self.player_instids)].sort_values(by='time')
        player_dst_events = events[events.dst_instid.isin(self.player_instids)].sort_values(by='time')
        boss_events = events[events.dst_instid.isin(self.boss_instids)]
        final_boss_events = events[events.src_instid == self.boss_instids[-1]]
        boss_power_events = boss_events[(boss_events.type == LogType.POWER) & (boss_events.value > 0)]

        deltas = boss_power_events.time - boss_power_events.time.shift(1)
        boss_power_events = boss_power_events.assign(delta = deltas)
        phase_splits = boss_power_events[boss_power_events.delta > 10000]
        phase_starts = [events.time.min()] + list(phase_splits.time)
        phase_ends = [int(x) for x in phase_splits.time - phase_splits.delta] + [events.time.max()]
        print("Autodetected phases: {0} {1}".format(phase_starts, phase_ends))
        self.phases = list(zip(phase_starts, phase_ends))

        return player_src_events, player_dst_events, boss_events, final_boss_events

    def preprocess_skills(self, skills, collector):
        collector.set_context_value(ContextType.SKILL_NAME, create_mapping(skills, 'name'))

    def __init__(self, encounter):
        self.debug = False
        self.boss_info = BOSSES[encounter.area_id]
        collector = Collector.root([Group.CATEGORY,
                                    Group.PHASE,
                                    Group.PLAYER,
                                    Group.SOURCE,
                                    Group.DESTINATION,
                                    Group.SKILL,
                                    Group.BUFF])

        #set up data structures
        events = encounter.events
        agents = encounter.agents
        skills = encounter.skills
        players, bosses, final_bosses = self.preprocess_agents(agents, collector)
        self.preprocess_skills(skills, collector)
        player_src_events, player_dst_events, boss_events, final_boss_events = self.preprocess_events(events)

        #time constraints
        start_event = events[events.state_change == parser.StateChange.LOG_START]
        start_timestamp = start_event['value'][0]
        start_time = start_event['time'][0]
        encounter_end = events.time.max()

        buff_data = BuffPreprocessor().process_events(start_time, encounter_end, skills, players, player_src_events)

        collector.with_key(Group.CATEGORY, "boss").run(self.collect_boss_key_events, events)
        collector.with_key(Group.CATEGORY, "status").run(self.collect_player_status, players)
        collector.with_key(Group.CATEGORY, "status").run(self.collect_player_key_events, player_src_events)
        collector.with_key(Group.CATEGORY, "damage").run(self.collect_outgoing_damage, player_src_events)
        collector.with_key(Group.CATEGORY, "damage").run(self.collect_incoming_damage, player_dst_events)
        collector.with_key(Group.CATEGORY, "buffs").run(self.collect_buffs_by_target, buff_data)

        encounter_collector = collector.with_key(Group.CATEGORY, "encounter")
        encounter_collector.add_data('start', start_timestamp, int)
        encounter_collector.add_data('duration', (encounter_end - start_time) / 1000, float)
        success = not final_boss_events[final_boss_events.state_change == parser.StateChange.CHANGE_DEAD].empty
        encounter_collector.add_data('success', success, bool)

        # saved as a JSON dump
        self.data = collector.all_data

    # Note: While this is just broken into areas with comments for now, we may want
    # a more concrete split in future

    # section: Agent stats (player/boss
    # subsection: boss stats
    def collect_invididual_boss_key_events(self, collector, events):
        #all_state_changes = events[events.state_change != parser.StateChange.NORMAL]
        enter_combat_time = only_entry(events[events.state_change == parser.StateChange.ENTER_COMBAT].time)
        death_time = only_entry(events[events.state_change == parser.StateChange.CHANGE_DEAD].time)
        collector.add_data("EnterCombat", enter_combat_time, int)
        collector.add_data("Death", death_time, int)

    def collect_boss_key_events(self, collector, events):
        boss_events = events[events.ult_src_instid.isin(self.boss_instids)]
        self.split_by_boss(collector,
                           self.collect_invididual_boss_key_events,
                           boss_events,
                           'ult_src_instid',
                           Group.BOSS)

    #subsection: player stats
    def collect_player_status(self, collector, players):
        # player archetypes
        players = players.assign(archetype=Archetype.POWER)
        players.loc[players.condition >= 7, 'archetype'] = Archetype.CONDI
        players.loc[players.toughness >= 7, 'archetype'] = Archetype.TANK
        players.loc[players.healing >= 7, 'archetype'] = Archetype.HEAL
        collector.group(self.collect_individual_player_status, players, ('name', Group.PLAYER))

    def collect_individual_player_status(self, collector, player):
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

    def collect_player_key_events(self, collector, events):
        # player archetypes
        player_only_events = events[events.src_instid.isin(self.player_instids)]
        self.split_by_player(collector, self.collect_individual_player_key_events, player_only_events, 'src_instid')

    def collect_individual_player_key_events(self, collector, events):
        # collector.add_data('profession_name', parser.AgentType(only_entry['prof']).name, str)
        enter_combat_time = only_entry(events[events.state_change == parser.StateChange.ENTER_COMBAT].time)
        death_time = only_entry(events[events.state_change == parser.StateChange.CHANGE_DEAD].time)
        collector.add_data("EnterCombat", enter_combat_time, int)
        collector.add_data("Death", death_time, int)

    #Split definitions
    def split_by_phase(self, collector, method, events):
        def collect_phase(name, phase_events):
            duration = float(phase_events['time'].max() - phase_events['time'].min())/1000.0
            if not duration > 0.001:
                duration = 0
            collector.set_context_value(ContextType.DURATION, duration)
            collector.with_key(Group.PHASE, name).run(method, phase_events)

        collect_phase("All", events)
        if self.debug:
            collect_phase("None", events[0:0])

        #Yes, this lists each phase individually even if there is only one
        #That's for consistency for things like:
        #Some things happen outside a phase.
        #Some fights have multiple phases, but you only get to phase one
        #Still want to list it as phase 1
        for i in range(0,len(self.phases)):
            phase = self.phases[i]
            phase_events = events[(events.time >= phase[0]) & (events.time <= phase[1])]
            collect_phase("{0}".format(i+1), phase_events)

    def split_by_player_groups(self, collector, method, events, player_column):
        collector.run(method, events)
        if self.debug:
            collector.with_key(Group.SUBGROUP, "*None").run(method, events[0:0])
        for subgroup in self.subgroups:
            subgroup_players = self.subgroups[subgroup]
            subgroup_events = events[events[player_column].isin(subgroup_players)]
            collector.with_key(Group.SUBGROUP, "{0}".format(subgroup)).run(
                method, subgroup_events)
        self.split_by_player(collector, method, events, player_column)

    def split_by_player(self, collector, method, events, player_column):
        collector.group(method, events,
                        (player_column, Group.PLAYER, mapped_to(ContextType.AGENT_NAME)))

    def split_by_agent(self, collector, method, events, group, enemy_column):
        boss_events = events[events[enemy_column].isin(self.boss_instids)]
        player_events = events[events[enemy_column].isin(self.player_instids)]

        non_add_instids = self.boss_instids
        add_events = events[events[enemy_column].isin(non_add_instids) != True]

        collector.with_key(group, "*All").run(method, events)
        collector.with_key(group, "*Boss").run(method, boss_events)
        collector.with_key(group, "*Players").run(method, player_events)
        collector.with_key(group, "*Adds").run(method, add_events)
        if self.debug:
            collector.with_key(group, "*None").run(method, events[0:0])
        if len(self.boss_instids) > 1:
            self.split_by_boss(collector, method, boss_events, enemy_column, group)

    def split_by_boss(self, collector, method, events, enemy_column, group):
        collector.group(method, events,
                (enemy_column, group, mapped_to(ContextType.AGENT_NAME)))

    def split_by_skill(self, collector, method, events):
        collector.group(method, events,
                        ('skillid', Group.SKILL, mapped_to(ContextType.SKILL_NAME)))

    #section: Outgoing damage stats filtering
    def collect_outgoing_damage(self, collector, player_events):
        damage_events = filter_damage_events(player_events)
        self.split_by_phase(collector, self.collect_phase_damage, damage_events)

    def collect_phase_damage(self, collector, damage_events):
        collector.with_key(Group.DESTINATION, "*All").run(self.collect_skill_data, damage_events)
        self.split_by_agent(collector,
                            self.collect_destination_damage,
                            damage_events,
                            Group.DESTINATION,
                            'dst_instid')



    def collect_destination_damage(self, collector, damage_events):
        collector.set_context_value(ContextType.TOTAL_DAMAGE_TO_DESTINATION,
                                    damage_events['damage'].sum())
        collector.set_context_value(ContextType.TOTAL_DAMAGE_FROM_SOURCE_TO_DESTINATION,
                                    damage_events['damage'].sum())
        self.split_by_player_groups(collector,
                                    self.aggregate_overall_damage_stats,
                                    damage_events,
                                    'ult_src_instid')

    def collect_skill_data(self, collector, damage_events):
        self.split_by_player(collector,
                             self.collect_player_skill_damage,
                             damage_events,
                             'ult_src_instid')

    def collect_player_skill_damage(self, collector, events):
        power_events = events[events.type == LogType.POWER]
        collector.set_context_value(ContextType.TOTAL_DAMAGE_FROM_SOURCE_TO_DESTINATION,
                                    events['damage'].sum())
        self.split_by_skill(collector, self.aggregate_power_damage_stats, power_events)
        self.split_by_skill(collector, self.aggregate_basic_damage_stats, events)

    #subsection incoming damage stat filtering
    def collect_incoming_damage(self, collector, player_events):
        damage_events = filter_damage_events(player_events)
        self.split_by_phase(collector, self.collect_phase_incoming_damage, damage_events)

    def collect_phase_incoming_damage(self, collector, damage_events):
        collector.set_context_value(ContextType.TOTAL_DAMAGE_FROM_SOURCE_TO_DESTINATION,
                                    damage_events['damage'].sum())
        source_collector =  collector.with_key(Group.SOURCE, "*All")
        self.split_by_player(source_collector, self.aggregate_basic_damage_stats, damage_events, 'dst_instid')
        self.split_by_player(source_collector, self.collect_player_incoming_skill_damage, damage_events, 'dst_instid')

    def collect_player_incoming_skill_damage(self, collector, events):
        collector.set_context_value(ContextType.TOTAL_DAMAGE_FROM_SOURCE_TO_DESTINATION,
                                    events['damage'].sum())
        self.split_by_skill(collector, self.aggregate_basic_damage_stats, events)

    #subsection: Aggregating damage
    def aggregate_overall_damage_stats(self, collector, events):
        power_events = events[events.type == LogType.POWER]
        condi_events = events[events.type == LogType.CONDI]
        self.aggregate_power_damage_stats(collector, power_events)
        self.aggregate_basic_damage_stats(collector, events)
        collector.add_data('power', power_events['damage'].sum(), int)
        collector.add_data('condi', condi_events['damage'].sum(), int)
        collector.add_data('power_dps', power_events['damage'].sum(), per_second(int))
        collector.add_data('condi_dps', condi_events['damage'].sum(), per_second(int))

    def aggregate_power_damage_stats(self, collector, events):
        collector.add_data('fifty', events['is_fifty'].mean(), percentage)
        collector.add_data('scholar', events['is_ninety'].mean(), percentage)
        collector.add_data('seaweed', events['is_moving'].mean(), percentage)

    def aggregate_basic_damage_stats(self, collector, events):
        collector.add_data('total', events['damage'].sum(), int)
        collector.add_data('dps', events['damage'].sum(), per_second(int))
        collector.add_data('percentage', events['damage'].sum(),
                           percentage_of(ContextType.TOTAL_DAMAGE_FROM_SOURCE_TO_DESTINATION))

    #Section: buff stats
    def collect_buffs_by_target(self, collector, buff_data):
         self.split_by_player(collector,
                              self.collect_buffs_by_type,
                              buff_data,
                              'player')

    def collect_buffs_by_type(self, collector, buff_data):
        #collector.with_key(Group.PHASE, "All").run(self.collect_buffs_by_target, buff_data);
        for buff_type in BUFF_TYPES:
            collector.set_context_value(ContextType.BUFF_TYPE, buff_type)
            buff_specific_data = buff_data[buff_data['buff'] ==  buff_type.code]
            diff_data = (buff_specific_data[['time']].diff(periods=-1, axis=0)[:-1] * -1).join(buff_specific_data[['stacks', 'time']], lsuffix="_diff")
            collector.with_key(Group.BUFF, buff_type.code).run(self.collect_buff, diff_data)

    def _slice_diff_data(self, diff_data, phase):
        pre_phase_row_index = diff_data[diff_data.time < phase[0]].index[-1]
        last_phase_row_index = diff_data[diff_data.time < phase[1]].index[-1]
        pre_phase_row = diff_data.loc[pre_phase_row_index : pre_phase_row_index + 1]
        if len(pre_phase_row) == 0:
            print("BOOO")
            return pre_phase_row
        phase_rows = diff_data.loc[pre_phase_row_index + 1 : last_phase_row_index]
        last_phase_row = diff_data.loc[last_phase_row_index : last_phase_row_index + 1]
        trunc_pre_phase_row = pre_phase_row.assign(time=phase[0], time_diff=pre_phase_row['time'].iloc[0] + pre_phase_row['time_diff'].iloc[0] - phase[0])
        trunc_last_phase_row = last_phase_row.assign(time_diff=phase[1] - last_phase_row['time'].iloc[0])
        phase_data = trunc_pre_phase_row.append(phase_rows).append(trunc_last_phase_row)
        return phase_data

    def collect_buff(self, collector, diff_data):
        phase = (self.phases[0][0], self.phases[-1][1])
        phase_data = self._slice_diff_data(diff_data, phase)
        collector.with_key(Group.PHASE, "All").run(self.collect_phase_buff, phase_data)

        for i in range(0, len(self.phases)):
            phase = self.phases[i]
            phase_data = self._slice_diff_data(diff_data, phase)
            collector.with_key(Group.PHASE, "{0}".format(i+1)).run(self.collect_phase_buff, phase_data)

    def collect_phase_buff(self, collector, diff_data):
        total_time = diff_data['time_diff'].sum()
        if total_time == 0:
            mean = 0
        else:
            mean = (diff_data['time_diff'] * diff_data['stacks']).sum() / total_time
        buff_type = collector.context_values[ContextType.BUFF_TYPE]
        if buff_type.stacking == StackType.INTENSITY:
            collector.add_data(None, mean)
        else:
            collector.add_data(None, mean, percentage)
