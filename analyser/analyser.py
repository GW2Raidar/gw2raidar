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
    METRICS = "Metrics"

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
    def __init__(self, name, boss_ids, sub_boss_ids=None, key_npc_ids = None, phases=None):
        self.name = name
        self.boss_ids = boss_ids
        self.sub_boss_ids = [] if sub_boss_ids is None else sub_boss_ids
        self.phases = [] if phases is None else phases
        self.key_npc_ids = [] if key_npc_ids is None else key_npc_ids

class Phase:
    def __init__(self, name, important,
                 phase_end_damage_stop=None,
                 phase_end_damage_start=None,
                 phase_end_health=None):
        self.name = name
        self.important = important
        self.phase_end_damage_stop = phase_end_damage_stop
        self.phase_end_damage_start = phase_end_damage_start
        self.phase_end_health = phase_end_health

    def find_end_time(self,
                      current_time,
                      damage_gaps,
                      health_updates,
                      skill_activations):
        end_time = None
        if self.phase_end_health is not None:
            relevant_health_updates = health_updates[(health_updates.time >= current_time) &
                                                     (health_updates.dst_agent >= self.phase_end_health * 100)]
            if relevant_health_updates.empty or health_updates['dst_agent'].min() > (self.phase_end_health + 2) * 100:
                return None
            end_time = current_time = int(relevant_health_updates['time'].iloc[-1])
            print("{0}: Detected health below {1} at time {2}".format(self.name, self.phase_end_health, current_time))

        if self.phase_end_damage_stop is not None:
            relevant_gaps = damage_gaps[(damage_gaps.time - damage_gaps.delta >= current_time) &
                                        (damage_gaps.delta > self.phase_end_damage_stop)]
            if not relevant_gaps.empty:
                end_time = current_time = int(relevant_gaps['time'].iloc[0] - relevant_gaps['delta'].iloc[0])
            elif int(damage_gaps.time.iloc[-1]) >= current_time:
                end_time = current_time = int(damage_gaps.time.iloc[-1])
            else:
                return None

            print("{0}: Detected gap of at least {1} at time {2}".format(self.name, self.phase_end_damage_stop, current_time))

        if self.phase_end_damage_start is not None:
            relevant_gaps = damage_gaps[(damage_gaps.time >= current_time) &
                                        (damage_gaps.delta > self.phase_end_damage_start)]
            if relevant_gaps.empty:
                return None
            end_time = current_time = int(relevant_gaps['time'].iloc[0])
            print("{0}: Detected gap of at least {1} ending at time {2}".format(self.name, self.phase_end_damage_start, current_time))
        return end_time

BOSS_ARRAY = [
    Boss('Vale Guardian', [0x3C4E], phases = [
        Phase("Phase 1", True, phase_end_health = 66, phase_end_damage_stop = 10000),
        Phase("First split", False, phase_end_damage_start = 10000),
        Phase("Phase 2", True, phase_end_health = 33, phase_end_damage_stop = 10000),
        Phase("Second split", False, phase_end_damage_start = 10000),
        Phase("Phase 3", True)
    ]),
    Boss('Gorseval', [0x3C45], phases = [
        Phase("Phase 1", True, phase_end_health = 66, phase_end_damage_stop = 10000),
        Phase("First souls", False, phase_end_damage_start = 10000),
        Phase("Phase 2", True, phase_end_health = 33, phase_end_damage_stop = 10000),
        Phase("Second souls", False, phase_end_damage_start = 10000),
        Phase("Phase 3", True)
    ]),
    Boss('Sabetha', [0x3C0F], phases = [
        Phase("Phase 1", True, phase_end_health = 75, phase_end_damage_stop = 10000),
        Phase("Kernan", False, phase_end_damage_start = 10000),
        Phase("Phase 2", True, phase_end_health = 50, phase_end_damage_stop = 10000),
        Phase("Knuckles", False, phase_end_damage_start = 10000),
        Phase("Phase 3", True, phase_end_health = 25, phase_end_damage_stop = 10000),
        Phase("Karde", False, phase_end_damage_start = 10000),
        Phase("Phase 4", True)
    ]),
    Boss('Slothasor', [0x3EFB], phases = [
        Phase("Phase 1", True, phase_end_health = 80, phase_end_damage_stop = 1000),
        Phase("Break 1", False, phase_end_damage_start = 1000),
        Phase("Phase 2", True, phase_end_health = 60, phase_end_damage_stop = 1000),
        Phase("Break 2", False, phase_end_damage_start = 1000),
        Phase("Phase 3", True, phase_end_health = 40, phase_end_damage_stop = 1000),
        Phase("Break 3", False, phase_end_damage_start = 1000),
        Phase("Phase 4", True, phase_end_health = 20, phase_end_damage_stop = 1000),
        Phase("Break 4", False, phase_end_damage_start = 1000),
        Phase("Phase 5", True, phase_end_health = 10, phase_end_damage_stop = 1000),
        Phase("Break 5", False, phase_end_damage_start = 1000),
        Phase("Phase 6", True)
    ]),
    Boss('Bandit Trio', [0x3ED8, 0x3F09, 0x3EFD], phases = [
        #Needs to be a little bit more robust, but it's trio - not the most important fight.
        #Phase("Clear 1", False, phase_end_health = 99),
        Phase("Berg", True, phase_end_damage_stop = 10000),
        Phase("Clear 2", False, phase_end_damage_start= 10000),
        Phase("Zane", True, phase_end_damage_stop = 10000),
        Phase("Clear 3", False, phase_end_damage_start = 10000),
        Phase("Narella", True, phase_end_damage_stop = 10000)
    ]),
    Boss('Matthias', [0x3EF3], phases = [
        #Will currently detect phases slightly early - but probably not a big deal?
        Phase("Ice", True, phase_end_health = 80),
        Phase("Fire", True, phase_end_health = 60),
        Phase("Rain", True, phase_end_health = 40),
        Phase("Abomination", True)
    ]),
    Boss('Keep Construct', [0x3F6B], phases = [
        # Needs more robust sub-phase mechanisms, but this should be on par with raid-heroes.
        Phase("Pre-burn 1", True, phase_end_damage_stop = 30000),
        Phase("Split 1", False, phase_end_damage_start = 30000),
        Phase("Burn 1", True, phase_end_health = 66, phase_end_damage_stop = 30000),
        Phase("Pacman 1", False, phase_end_damage_start = 30000),
        Phase("Pre-burn 2", True, phase_end_damage_stop = 30000),
        Phase("Split 2", False, phase_end_damage_start = 30000),
        Phase("Burn 2", True, phase_end_health = 33, phase_end_damage_stop = 30000),
        Phase("Pacman 2", False, phase_end_damage_start = 30000),
        Phase("Pre-burn 3", True, phase_end_damage_stop = 30000),
        Phase("Split 3", False, phase_end_damage_start = 30000),
        Phase("Burn 3", True)
    ]),
    Boss('Xera', [0x3F76, 0x3F9E], phases = [
        Phase("Phase 1", True, phase_end_health = 51, phase_end_damage_stop = 30000),
        Phase("Leyline", False, phase_end_damage_start = 30000),
        Phase("Phase 2", True),
    ]),
    Boss('Cairn', [0x432A]),
    Boss('Mursaat Overseer', [0x4314]),
    Boss('Samarog', [0x4324], phases = [
        Phase("Phase 1", True, phase_end_health = 66, phase_end_damage_stop = 10000),
        Phase("First split", False, phase_end_damage_start = 10000),
        Phase("Phase 2", True, phase_end_health = 33, phase_end_damage_stop = 10000),
        Phase("Second split", False, phase_end_damage_start = 10000),
        Phase("Phase 3", True, phase_end_health=1)
    ]),
    Boss('Deimos', [0x4302], key_npc_ids=[17126], phases = [
        Phase("Phase 1", True, phase_end_health = 10, phase_end_damage_stop = 20000),
        Phase("Phase 2", True)
    ]),
]
BOSSES = {boss.boss_ids[0]: boss for boss in BOSS_ARRAY}

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
        dfc[new_name] = dfc[name].apply(func)
    with pd.option_context('display.max_rows', 9999999, 'display.max_columns', 500, 'display.height', 100000, 'display.width', 100000):
        print(dfc)

class Analyser:
    def preprocess_agents(self, agents, collector):
        players = agents[agents.party != 0]
        bosses = agents[agents.prof.isin(self.boss_info.boss_ids)]
        final_bosses = agents[agents.prof == self.boss_info.boss_ids[-1]]

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
        from_boss_events = events[events.src_instid.isin(self.boss_instids)]
        to_boss_events = events[events.dst_instid.isin(self.boss_instids)]
        from_final_boss_events = from_boss_events[from_boss_events.src_instid.isin(self.final_boss_instids)]

        #construct frame of all power damage to boss, including deltas since last hit.
        boss_power_events = to_boss_events[(to_boss_events.type == LogType.POWER) & (to_boss_events.value > 0)]
        deltas = boss_power_events.time - boss_power_events.time.shift(1)
        boss_power_events = boss_power_events.assign(delta = deltas)

        #construct frame of all health updates from the boss
        health_updates = from_boss_events[from_boss_events.state_change == parser.StateChange.HEALTH_UPDATE]

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

        #set up data structures
        events = encounter.events
        agents = encounter.agents
        skills = encounter.skills
        players, bosses, final_bosses = self.preprocess_agents(agents, collector)
        self.preprocess_skills(skills, collector)
        player_src_events, player_dst_events, boss_events, final_boss_events = self.preprocess_events(events)
        player_only_events = player_src_events[player_src_events.src_instid.isin(self.player_instids)]

        #time constraints
        start_event = events[events.state_change == parser.StateChange.LOG_START]
        start_timestamp = start_event['value'][0]
        start_time = start_event['time'][0]
        encounter_end = events.time.max()
        down_events = self.assemble_down_data(player_only_events, players, encounter_end)
        dead_events = self.assemble_dead_data(player_only_events, players, encounter_end)

        buff_data = BuffPreprocessor().process_events(start_time, encounter_end, skills, players, player_src_events)
        
        collector.with_key(Group.CATEGORY, "boss").run(self.collect_boss_key_events, events)
        collector.with_key(Group.CATEGORY, "status").run(self.collect_player_status, players)
        collector.with_key(Group.CATEGORY, "status").run(self.collect_player_key_events, player_src_events)
        collector.with_key(Group.CATEGORY, "combat").with_key(Group.METRICS, "damage").run(            self.collect_outgoing_damage, player_src_events)
        collector.with_key(Group.CATEGORY, "combat").with_key(Group.METRICS, "damage").run(self.collect_incoming_damage, player_dst_events)
        collector.with_key(Group.CATEGORY, "combat").with_key(Group.METRICS, "buffs").run(self.collect_incoming_buffs, buff_data)
        collector.with_key(Group.CATEGORY, "combat").with_key(Group.METRICS, "events").run(self.collect_player_combat_events, player_only_events)
        collector.with_key(Group.CATEGORY, "combat").with_key(Group.METRICS, "events").run(self.collect_player_state_duration('down_time'), down_events)
        collector.with_key(Group.CATEGORY, "combat").with_key(Group.METRICS, "events").run(self.collect_player_state_duration('dead_time'), dead_events)

        encounter_collector = collector.with_key(Group.CATEGORY, "encounter")
        encounter_collector.add_data('start', start_timestamp, int)
        encounter_collector.add_data('start_tick', start_time, int)
        encounter_collector.add_data('end_tick', encounter_end, int)
        encounter_collector.add_data('duration', (encounter_end - start_time) / 1000, float)
        success = not final_boss_events[(final_boss_events.state_change == parser.StateChange.CHANGE_DEAD)
                                        | (final_boss_events.state_change == parser.StateChange.DESPAWN)].empty


        encounter_collector.add_data('phase_order', [name for name,start,end in self.phases])
        for phase in self.phases:
            phase_collector = encounter_collector.with_key(Group.PHASE, phase[0])
            phase_collector.add_data('start_tick', phase[1], int)
            phase_collector.add_data('end_tick', phase[2], int)
            phase_collector.add_data('duration', (phase[2] - phase[1]) / 1000, float)

        #If we completed all phases, and the key npcs survived, and at least one player survived... assume we succeeded
        if self.boss_info.key_npc_ids and len(self.phases) == len(list(filter(lambda a: a.important, self.boss_info.phases))):
            end_state_changes = [parser.StateChange.CHANGE_DEAD, parser.StateChange.DESPAWN]
            key_npc_events = events[events.src_instid.isin(self.boss_info.key_npc_ids)]
            if key_npc_events[(key_npc_events.state_change == parser.StateChange.CHANGE_DEAD)].empty:
                dead_players = player_src_events[(player_src_events.src_instid.isin(self.player_instids)) &
                                                 (player_src_events.state_change.isin(end_state_changes))].src_instid.unique()
                surviving_players = list(filter(lambda a: a not in dead_players, self.player_instids))
                if surviving_players:
                    success = True

        encounter_collector.add_data('success', success, bool)
        print(success)

        # saved as a JSON dump
        self.data = collector.all_data
        
    def assemble_down_data(self, events, players, encounter_end):
        # Get Up/Down/Death events
        down_events = events[(events['state_change'] == parser.StateChange.CHANGE_DOWN)
                             |(events['state_change'] == parser.StateChange.CHANGE_DEAD)
                             |(events['state_change'] == parser.StateChange.CHANGE_UP)]

        # Produce down state 
        raw_data = np.array([np.arange(0, dtype=int)] * 4, dtype=int).T

        for player in list(players.index):
            data = np.array([np.arange(0)] * 3).T
            relevent_events = down_events[down_events['src_instid'] == player]
            down = False
            start_time = 0
            for event in relevent_events.itertuples():
                if (not down) & (event.state_change == parser.StateChange.CHANGE_DOWN):
                    start_time = event.time
                    down = True
                elif down & (event.state_change == parser.StateChange.CHANGE_UP):
                    data = np.append(data, [[start_time, event.time - start_time, 1]], axis=0)
                    down = False
                elif down & (event.state_change == parser.StateChange.CHANGE_DEAD):
                    data = np.append(data, [[start_time, event.time - start_time, 0]], axis=0)
                    down = False
            
            if down:
                np.append = np.append(data, [[start_time, encounter_end, encounter_end - start_time, 1]], axis=0)

            data = np.c_[[player] * data.shape[0], data]
            raw_data = np.r_[raw_data, data]

        return pd.DataFrame(columns = ['player', 'time', 'duration', 'recovered'], data = raw_data)
    
    def assemble_dead_data(self, events, players, encounter_end):
        # Get Up/Death events
        down_events = events[(events['state_change'] == parser.StateChange.CHANGE_DEAD)
                             |(events['state_change'] == parser.StateChange.CHANGE_UP)]

        # Produce dead state 
        raw_data = np.array([np.arange(0, dtype=int)] * 3, dtype=int).T

        for player in list(players.index):
            data = np.array([np.arange(0)] * 2).T
            relevent_events = down_events[down_events['src_instid'] == player]
            dead = False
            start_time = 0
            for event in relevent_events.itertuples():
                if (not dead) & (event.state_change == parser.StateChange.CHANGE_DEAD):
                    start_time = event.time
                    dead = True
                elif dead & (event.state_change == parser.StateChange.CHANGE_UP):
                    data = np.append(data, [[start_time, event.time - start_time]], axis=0)
                    dead = False
            
            if dead:
                data = np.append(data, [[start_time, encounter_end - start_time]], axis=0)

            data = np.c_[[player] * data.shape[0], data]
            raw_data = np.r_[raw_data, data]

        return pd.DataFrame(columns = ['player', 'time', 'duration'], data = raw_data)

    # Note: While this is just broken into areas with comments for now, we may want
    # a more concrete split in future

    # section: Agent stats (player/boss
    # subsection: player events
    def collect_player_state_duration(self, tag):
        def collect_player_state_duration_inner(collector, events):
            self.split_by_player_groups(collector, self.collect_player_state_duration_by_phase(tag), events, 'player')  
        return collect_player_state_duration_inner
        
    def collect_player_state_duration_by_phase(self, tag):
        def collect_player_state_duration_by_phase_inner(collector, events):
            self.split_duration_event_by_phase(collector, self.collect_state_duration(tag), events)  
        return collect_player_state_duration_by_phase_inner
        
    def collect_state_duration(self, tag):
        def inner_collect_state_duration(collector, events):
            collector.add_data(tag, events['duration'].sum())
        return inner_collect_state_duration
    
    def collect_player_combat_events(self, collector, events):
        self.split_by_player_groups(collector, self.collect_combat_events_by_phase, events, 'src_instid')  
    
    def collect_combat_events_by_phase(self, collector, events):
        self.split_by_phase(collector, self.collect_combat_events, events)  
        
    def collect_combat_events(self, collector, events):
        death_events = len(events[events['state_change'] == parser.StateChange.CHANGE_DEAD])
        down_events = len(events[events['state_change'] == parser.StateChange.CHANGE_DOWN])
        disconnect_events = len(events[events['state_change'] == parser.StateChange.DESPAWN])
        collector.add_data('deaths', death_events, int)
        collector.add_data('downs', down_events, int)
        collector.add_data('disconnects', disconnect_events, int)
        
    def split_duration_event_by_phase(self, collector, method, events):
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
            
    # subsection: boss stats
    def collect_individual_boss_key_events(self, collector, events):
        enter_combat_time = only_entry(events[events.state_change == parser.StateChange.ENTER_COMBAT].time)
        death_time = only_entry(events[events.state_change == parser.StateChange.CHANGE_DEAD].time)
        collector.add_data("EnterCombat", enter_combat_time, int)
        collector.add_data("Death", death_time, int)

    def collect_boss_key_events(self, collector, events):
        boss_events = events[events.ult_src_instid.isin(self.boss_instids)]
        self.split_by_boss(collector,
                           self.collect_individual_boss_key_events,
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
            phase_events = events[(events.time >= phase[1]) & (events.time <= phase[2])]
            collect_phase(phase[0], phase_events)

    def split_by_player_groups(self, collector, method, events, player_column):
        collector.with_key(Group.SUBGROUP, "*All").run(method, events)
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
        self.split_by_player_groups(source_collector, self.aggregate_basic_damage_stats, damage_events, 'dst_instid')
        self.split_by_player_groups(source_collector, self.collect_player_incoming_skill_damage, damage_events, 'dst_instid')

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
        collector.add_data('flanking', events['is_flanking'].mean(), percentage)

    def aggregate_basic_damage_stats(self, collector, events):
        collector.add_data('total', events['damage'].sum(), int)
        collector.add_data('dps', events['damage'].sum(), per_second(int))
        collector.add_data('percentage', events['damage'].sum(),
                           percentage_of(ContextType.TOTAL_DAMAGE_FROM_SOURCE_TO_DESTINATION))

    #Section: buff stats
    def collect_incoming_buffs(self, collector, buff_data):
        source_collector = collector.with_key(Group.SOURCE, "*All");
        self.collect_buffs_by_target(source_collector, buff_data)
    
    def collect_buffs_by_target(self, collector, buff_data):
        self.split_by_player_groups(collector, self.collect_buffs_by_type, buff_data, 'player')        

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
        phase_data = self._split_buff_by_phase(diff_data, self.start_time, self.end_time)
        collector.with_key(Group.PHASE, "All").run(self.collect_phase_buff, phase_data)

        for i in range(0, len(self.phases)):
            phase = self.phases[i]
            phase_data = self._split_buff_by_phase(diff_data, phase[1], phase[2])
            collector.with_key(Group.PHASE, "{0}".format(phase[0])).run(self.collect_phase_buff, phase_data)

    def collect_phase_buff(self, collector, diff_data):
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
