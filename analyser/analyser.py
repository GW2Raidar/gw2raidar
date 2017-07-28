from enum import IntEnum
from evtcparser import *
import pandas as pd
import numpy as np
from functools import reduce
from .collector import *
from .buffs import *
from .splits import *
from .bossmetrics import *
from .bosses import *

# DEBUG
from sys import exit
import timeit

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
    SUPPORT = 5

class Elite(IntEnum):
    CORE = 0
    HEART_OF_THORNS = 1

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

def print_frame(df, *mods):
    dfc = df.copy()
    for name,new_name,func in mods:
        dfc[new_name] = (dfc.index if name == 'index' else dfc[name]).apply(func)
    with pd.option_context('display.max_rows', 9999999, 'display.max_columns', 500, 'display.height', 100000, 'display.width', 100000):
        print(dfc)

class Analyser:
    def preprocess_agents(self, agents, collector, events):
        #Add hit count column
        agents_that_get_hit_a_lot = events[(events.type == LogType.POWER)
                                & (events.value > 0)][
            ['dst_instid']].groupby('dst_instid').size().rename('hit_count')
        agents = agents.join(agents_that_get_hit_a_lot)
        agents.hit_count.fillna(0, inplace=True)

        #identify specific ones we care about
        players = agents[agents.party != 0]
        bosses = agents[(agents.prof.isin(self.boss_info.boss_ids)) |
                        (self.boss_info.has_structure_boss
                         & (agents.prof < 0)
                         & (agents.hit_count >= 100))]
        final_bosses = agents[agents.prof == self.boss_info.boss_ids[-1]]

        #set up important preprocessed data
        self.subgroups = dict([(number, subgroup.index.values) for number, subgroup in players.groupby("party")])
        self.player_instids = players.index.values
        self.boss_instids = bosses.index.values

        print(self.boss_instids)
        self.final_boss_instids = final_bosses.index.values
        collector.set_context_value(ContextType.AGENT_NAME, create_mapping(agents, 'name'))
        return players, bosses, final_bosses

    def preprocess_events(self, events):
        #experimental phase calculations
        events['ult_src_instid'] = events.src_master_instid.where(
            events.src_master_instid != 0, events.src_instid)
        player_src_events = events[events.ult_src_instid.isin(self.player_instids)].sort_values(by='time')

        player_dst_events = events[events.dst_instid.isin(self.player_instids)].sort_values(by='time')
        from_boss_events = events[events.src_instid.isin(self.boss_instids)]
        to_boss_events = events[events.dst_instid.isin(self.boss_instids)]
        from_final_boss_events = from_boss_events[from_boss_events.src_instid.isin(self.final_boss_instids)]

        #construct frame of all power damage to boss, including deltas since last hit.
        boss_power_events = to_boss_events[(to_boss_events.type == LogType.POWER) & (to_boss_events.value > 0)]
        deltas = boss_power_events.time - boss_power_events.time.shift(1)
        boss_power_events = boss_power_events.assign(delta = deltas)
        #print_frame(boss_power_events[boss_power_events.delta >= 1000])
        #construct frame of all health updates from the boss
        health_updates = from_boss_events[from_boss_events.state_change == parser.StateChange.HEALTH_UPDATE]
        #print_frame(health_updates)

        #construct frame of all boss skill activations
        boss_skill_activations = from_boss_events[from_boss_events.is_activation != parser.Activation.NONE]
        def process_end_condition(end_condition, phase_end):
            pass

        #Determine phases...
        self.start_time = events.time.min()
        self.end_time = events.time.max()
        current_time = self.start_time
        phase_starts = []
        phase_ends = []
        phase_names = []
        for phase in self.boss_info.phases:
            phase_names.append(phase.name)
            phase_starts.append(current_time)
            phase_end = phase.find_end_time(current_time,
                                            boss_power_events,
                                            health_updates,
                                            boss_skill_activations)
            if phase_end is None:
                break
            phase_ends.append(phase_end)
            current_time = phase_end
        phase_ends.append( self.end_time)

        def print_phase(phase):
            print("{0}: {1} - {2} ({3})".format(phase[0],
                                                phase[1] - self.start_time,
                                                phase[2] - self.start_time,
                                                phase[2] - phase[1]))

        all_phases = list(zip(phase_names, phase_starts, phase_ends))
        print("Autodetected phases:")
        list(map(print_phase, all_phases))
        self.phases = [a for (a,i) in zip(all_phases, self.boss_info.phases) if i.important]
        print("Important phases:")
        list(map(print_phase, self.phases))

        return player_src_events, player_dst_events, from_boss_events, from_final_boss_events

    def preprocess_skills(self, skills, collector):
        collector.set_context_value(ContextType.SKILL_NAME, create_mapping(skills, 'name'))

    def __init__(self, encounter):
        self.debug = False
        self.boss_info = BOSSES[encounter.area_id]
        collector = Collector.root([Group.CATEGORY,
                                    Group.PHASE,
                                    Group.PLAYER,
                                    Group.SUBGROUP,
                                    Group.METRICS,
                                    Group.SOURCE,
                                    Group.DESTINATION,
                                    Group.SKILL,
                                    Group.BUFF,

                                    ])

        #print_frame(encounter.duplicate_id_agents)

        #set up data structures
        events = assign_event_types(encounter.events)
        agents = encounter.agents
        skills = encounter.skills
        players, bosses, final_bosses = self.preprocess_agents(agents, collector, events)
        self.preprocess_skills(skills, collector)
        self.players = players
        player_src_events, player_dst_events, boss_events, final_boss_events = self.preprocess_events(events)
        player_only_events = player_src_events[player_src_events.src_instid.isin(self.player_instids)]

        #time constraints
        start_event = events[events.state_change == parser.StateChange.LOG_START]
        start_timestamp = start_event['value'][0]
        start_time = start_event['time'][0]
        encounter_end = events.time.max()
        state_events = self.assemble_state_data(player_only_events, players, encounter_end)
        self.state_events = state_events

        BossMetricAnalyser(agents, self.subgroups, self.players, bosses, self.phases).gather_boss_specific_stats(events, collector)
        buff_data = BuffPreprocessor().process_events(start_time, encounter_end, skills, players, player_src_events)

        collector.with_key(Group.CATEGORY, "boss").run(self.collect_boss_key_events, events)
        collector.with_key(Group.CATEGORY, "status").run(self.collect_player_status, players)
        collector.with_key(Group.CATEGORY, "status").run(self.collect_player_key_events, player_src_events)
        collector.with_key(Group.CATEGORY, "combat").with_key(Group.METRICS, "damage").run(self.collect_outgoing_damage, player_src_events)
        collector.with_key(Group.CATEGORY, "combat").with_key(Group.METRICS, "damage").run(self.collect_incoming_damage, player_dst_events)
        collector.with_key(Group.CATEGORY, "combat").with_key(Group.METRICS, "buffs").run(self.collect_incoming_buffs, buff_data)
        collector.with_key(Group.CATEGORY, "combat").with_key(Group.METRICS, "events").run(self.collect_player_combat_events, player_only_events)
        collector.with_key(Group.CATEGORY, "combat").with_key(Group.METRICS, "events").run(self.collect_player_state_duration, state_events)



        encounter_collector = collector.with_key(Group.CATEGORY, "encounter")
        encounter_collector.add_data('evtc_version', encounter.version)
        encounter_collector.add_data('start', start_timestamp, int)
        encounter_collector.add_data('start_tick', start_time, int)
        encounter_collector.add_data('end_tick', encounter_end, int)
        encounter_collector.add_data('duration', (encounter_end - start_time) / 1000, float)
        success = not final_boss_events[(final_boss_events.state_change == parser.StateChange.CHANGE_DEAD)].empty


        encounter_collector.add_data('phase_order', [name for name,start,end in self.phases])
        for phase in self.phases:
            phase_collector = encounter_collector.with_key(Group.PHASE, phase[0])
            phase_collector.add_data('start_tick', phase[1], int)
            phase_collector.add_data('end_tick', phase[2], int)
            phase_collector.add_data('duration', (phase[2] - phase[1]) / 1000, float)

        #If we completed all phases, and the key npcs survived, and at least one player survived... assume we succeeded
        if self.boss_info.despawns_instead_of_dying and len(self.phases) == len(list(filter(lambda a: a.important, self.boss_info.phases))):
            end_state_changes = [parser.StateChange.CHANGE_DEAD, parser.StateChange.DESPAWN]
            key_npc_events = events[events.src_instid.isin(self.boss_info.key_npc_ids)]
            if key_npc_events[(key_npc_events.state_change == parser.StateChange.CHANGE_DEAD)].empty:
                dead_players = player_src_events[(player_src_events.src_instid.isin(self.player_instids)) &
                                                 (player_src_events.state_change.isin(end_state_changes))].src_instid.unique()
                surviving_players = list(filter(lambda a: a not in dead_players, self.player_instids))
                if surviving_players:
                    success = True

        encounter_collector.add_data('success', success, bool)

        # saved as a JSON dump
        self.data = collector.all_data

    def assemble_state_data(self, events, players, encounter_end):
        # Get Up/Down/Death events
        down_events = events[(events['state_change'] == parser.StateChange.CHANGE_DOWN)
                            |(events['state_change'] == parser.StateChange.CHANGE_DEAD)
                            |(events['state_change'] == parser.StateChange.CHANGE_UP)
                            |(events['state_change'] == parser.StateChange.DESPAWN)
                            |(events['state_change'] == parser.StateChange.SPAWN)].sort_values(by='time')

        # Produce down state
        raw_data = np.array([np.arange(0, dtype=int)] * 5, dtype=int).T

        for player in list(players.index):
            data = np.array([np.arange(0)] * 4).T
            relevent_events = down_events[down_events['src_instid'] == player]

            state = parser.StateChange.CHANGE_UP
            start_time = 0
            for event in relevent_events.itertuples():

                if state == parser.StateChange.CHANGE_DOWN:
                    data = np.append(data, [[start_time, parser.StateChange.CHANGE_DOWN, event.time - start_time, (event.state_change == parser.StateChange.CHANGE_UP)]], axis=0)
                elif state == parser.StateChange.CHANGE_DEAD:
                    data = np.append(data, [[start_time, parser.StateChange.CHANGE_DEAD, event.time - start_time, 0]], axis=0)
                elif state == parser.StateChange.DESPAWN:
                    data = np.append(data, [[start_time, parser.StateChange.DESPAWN, event.time - start_time, 0]], axis=0)

                if event.state_change != parser.StateChange.SPAWN:
                    state = event.state_change;
                start_time = event.time

            if state != parser.StateChange.CHANGE_UP:
                data = np.append(data, [[start_time, state, encounter_end - start_time, 1]], axis=0)

            data = np.c_[[player] * data.shape[0], data]
            raw_data = np.r_[raw_data, data]

        return pd.DataFrame(columns = ['player', 'time', 'state', 'duration', 'recovered'], data = raw_data)

    # Note: While this is just broken into areas with comments for now, we may want
    # a more concrete split in future

    # section: Agent stats (player/boss
    # subsection: player events
    def collect_player_state_duration(self, collector, events):
        split_by_player_groups(collector, self.collect_player_state_duration_by_phase, events, 'player', self.subgroups, self.players)

    def collect_player_state_duration_by_phase(self, collector, events):
        split_duration_event_by_phase(collector, self.collect_state_duration, events, self.phases)

    def collect_state_duration(self, collector, events):
        collector.add_data('down_time', events[events['state'] == parser.StateChange.CHANGE_DOWN]['duration'].sum())
        collector.add_data('dead_time', events[events['state'] == parser.StateChange.CHANGE_DEAD]['duration'].sum())
        collector.add_data('disconnect_time', events[events['state'] == parser.StateChange.DESPAWN]['duration'].sum())

    def collect_player_combat_events(self, collector, events):
        split_by_player_groups(collector, self.collect_combat_events_by_phase, events, 'src_instid', self.subgroups, self.players)

    def collect_combat_events_by_phase(self, collector, events):
        split_by_phase(collector, self.collect_combat_events, events, self.phases)

    def collect_combat_events(self, collector, events):
        death_events = len(events[events['state_change'] == parser.StateChange.CHANGE_DEAD])
        down_events = len(events[events['state_change'] == parser.StateChange.CHANGE_DOWN])
        disconnect_events = len(events[events['state_change'] == parser.StateChange.DESPAWN])
        collector.add_data('deaths', death_events, int)
        collector.add_data('downs', down_events, int)
        collector.add_data('disconnects', disconnect_events, int)

    # subsection: boss stats
    def collect_individual_boss_key_events(self, collector, events):
        enter_combat_time = only_entry(events[events.state_change == parser.StateChange.ENTER_COMBAT].time)
        death_time = only_entry(events[events.state_change == parser.StateChange.CHANGE_DEAD].time)
        collector.add_data("EnterCombat", enter_combat_time, int)
        collector.add_data("Death", death_time, int)

    def collect_boss_key_events(self, collector, events):
        boss_events = events[events.ult_src_instid.isin(self.boss_instids)]
        split_by_boss(collector,
                           self.collect_individual_boss_key_events,
                           boss_events,
                           'ult_src_instid',
                           Group.BOSS)

    #subsection: player stats
    def collect_player_status(self, collector, players):
        # player archetypes
        players = players.assign(archetype=Archetype.POWER)
        players.loc[players.condition >= 5, 'archetype'] = Archetype.CONDI
        players.loc[(players.toughness >= 5) | (players.healing >= 5), 'archetype'] = Archetype.SUPPORT
        collector.group(self.collect_individual_player_status, players, ('name', Group.PLAYER))

    def collect_individual_player_status(self, collector, player):
        only_entry = player.iloc[0]
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
        split_by_player(collector, self.collect_individual_player_key_events, player_only_events, 'src_instid', self.players)

    def collect_individual_player_key_events(self, collector, events):
        # collector.add_data('profession_name', parser.AgentType(only_entry['prof']).name, str)
        enter_combat_time = only_entry(events[events.state_change == parser.StateChange.ENTER_COMBAT].time)
        death_time = only_entry(events[events.state_change == parser.StateChange.CHANGE_DEAD].time)
        collector.add_data("EnterCombat", enter_combat_time, int)
        collector.add_data("Death", death_time, int)

    #section: Outgoing damage stats filtering
    def collect_outgoing_damage(self, collector, player_events):
        damage_events = filter_damage_events(player_events)
        split_by_phase(collector, self.collect_phase_damage, damage_events, self.phases)

    def collect_phase_damage(self, collector, damage_events):
        collector.with_key(Group.DESTINATION, "*All").run(self.collect_skill_data, damage_events)
        split_by_agent(collector,
                            self.collect_destination_damage,
                            damage_events,
                            Group.DESTINATION,
                            'dst_instid', self.boss_instids, self.player_instids)



    def collect_destination_damage(self, collector, damage_events):
        collector.set_context_value(ContextType.TOTAL_DAMAGE_TO_DESTINATION,
                                    damage_events['damage'].sum())
        collector.set_context_value(ContextType.TOTAL_DAMAGE_FROM_SOURCE_TO_DESTINATION,
                                    damage_events['damage'].sum())
        split_by_player_groups(collector,
                                    self.aggregate_overall_damage_stats,
                                    damage_events,
                                    'ult_src_instid', self.subgroups, self.players)

    def collect_skill_data(self, collector, damage_events):
        split_by_player(collector,
                             self.collect_player_skill_damage,
                             damage_events,
                             'ult_src_instid', self.players)

    def collect_player_skill_damage(self, collector, events):
        power_events = events[events.type == LogType.POWER]
        collector.set_context_value(ContextType.TOTAL_DAMAGE_FROM_SOURCE_TO_DESTINATION,
                                    events['damage'].sum())
        split_by_skill(collector, self.aggregate_power_damage_stats, power_events)
        split_by_skill(collector, self.aggregate_basic_damage_stats, events)

    #subsection incoming damage stat filtering
    def collect_incoming_damage(self, collector, player_events):
        damage_events = filter_damage_events(player_events)
        split_by_phase(collector, self.collect_phase_incoming_damage, damage_events, self.phases)

    def collect_phase_incoming_damage(self, collector, damage_events):
        collector.set_context_value(ContextType.TOTAL_DAMAGE_FROM_SOURCE_TO_DESTINATION,
                                    damage_events['damage'].sum())
        source_collector =  collector.with_key(Group.SOURCE, "*All")
        split_by_player_groups(source_collector, self.aggregate_basic_damage_stats, damage_events, 'dst_instid', self.subgroups, self.players)
        split_by_player_groups(source_collector, self.collect_player_incoming_skill_damage, damage_events, 'dst_instid', self.subgroups, self.players)

    def collect_player_incoming_skill_damage(self, collector, events):
        collector.set_context_value(ContextType.TOTAL_DAMAGE_FROM_SOURCE_TO_DESTINATION,
                                    events['damage'].sum())
        split_by_skill(collector, self.aggregate_basic_damage_stats, events)

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
        collector.add_data('flanking', events['is_flanking'].mean(), percentage)
        collector.add_data('crit', (events.result == parser.Result.CRIT).mean(), percentage)

    def aggregate_basic_damage_stats(self, collector, events):
        collector.add_data('total', events['damage'].sum(), int)
        collector.add_data('dps', events['damage'].sum(), per_second(int))
        collector.add_data('percentage', events['damage'].sum(),
                           percentage_of(ContextType.TOTAL_DAMAGE_FROM_SOURCE_TO_DESTINATION))

    #Section: buff stats
    def collect_incoming_buffs(self, collector, buff_data):
        source_collector = collector.with_key(Group.SOURCE, "*All");
        phase_data = self._split_buff_by_phase(buff_data, self.start_time, self.end_time)
        source_collector.with_key(Group.PHASE, "All").run(self.collect_buffs_by_target, phase_data)

        for i in range(0, len(self.phases)):
            phase = self.phases[i]
            phase_data = self._split_buff_by_phase(buff_data, phase[1], phase[2])
            source_collector.with_key(Group.PHASE, "{0}".format(phase[0])).run(self.collect_buffs_by_target, phase_data)

    def collect_buffs_by_target(self, collector, buff_data):
        split_by_player_groups(collector, self.collect_buffs_by_type, buff_data, 'player', self.subgroups, self.players)

    def collect_buffs_by_type(self, collector, buff_data):
        #collector.with_key(Group.PHASE, "All").run(self.collect_buffs_by_target, buff_data);
        for buff_type in BUFF_TYPES:
            collector.set_context_value(ContextType.BUFF_TYPE, buff_type)
            buff_specific_data = buff_data[buff_data['buff'] ==  buff_type.code]
            collector.with_key(Group.BUFF, buff_type.code).run(self.collect_buff, buff_specific_data)

    def _split_buff_by_phase(self, diff_data, start, end):
        across_phase = diff_data[(diff_data['time'] < start) & (diff_data['time'] + diff_data['duration'] > end)]

        #HACK: review why copy?
        before_phase = diff_data[(diff_data['time'] < start) & (diff_data['time'] + diff_data['duration'] > start) & (diff_data['time'] + diff_data['duration'] <= end)].copy()
        main_phase = diff_data[(diff_data['time'] >= start) & (diff_data['time'] + diff_data['duration'] <= end)]
        after_phase = diff_data[(diff_data['time'] >= start) & (diff_data['time'] < end) & (diff_data['time'] + diff_data['duration'] > end)]

        across_phase = across_phase.assign(time = start, duration = end - start, stripped = 0)

        before_phase.loc[:, 'duration'] = before_phase['duration'] + before_phase['time'] - start
        before_phase = before_phase.assign(time = start, stripped = 0)

        after_phase = after_phase.assign(duration = end)
        after_phase.loc[:, 'duration'] = after_phase['duration'] - after_phase['time']
        return across_phase.append(before_phase).append(main_phase).append(after_phase)

    def collect_buff(self, collector, diff_data):
        total_time = diff_data['duration'].sum()
        if total_time == 0:
            mean = 0
        else:
            mean = (diff_data['duration'] * diff_data['stacks']).sum() / total_time
        buff_type = collector.context_values[ContextType.BUFF_TYPE]
        if buff_type.stacking == StackType.INTENSITY:
            collector.add_data(None, mean)
        else:
            collector.add_data(None, mean, percentage)
