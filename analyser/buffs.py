from enum import IntEnum
from evtcparser import *
import pandas as pd
import numpy as np

class StackType(IntEnum):
    INTENSITY = 0
    DURATION = 1

class BuffType:
    def __init__(self, name, code, skillid, stacking, capacity, arch_uptime = 100000000, arch_support_power = 0):
        self.name = name
        self.code = code
        self.skillid = skillid
        self.stacking = stacking
        self.capacity = capacity
        self.arch_uptime = arch_uptime
        self.arch_support_power = arch_support_power
        
BUFF_TYPES = [
        # General Boons
        BuffType('Might', 'might', [740], StackType.INTENSITY, 25, 40, 5),
        BuffType('Quickness', 'quickness', [1187], StackType.DURATION, 5, 150, 5),
        BuffType('Fury', 'fury', [725], StackType.DURATION, 9, 150, 1),
        BuffType('Protection', 'protection', [717], StackType.DURATION, 5, 200, 2),
        BuffType('Alacrity', 'alacrity', [30328], StackType.DURATION, 9, 150, 5),
        BuffType('Retaliation', 'retaliation', [873], StackType.DURATION, 5),
        BuffType('Regeneration', 'regen', [718], StackType.DURATION, 5),
        BuffType('Aegis', 'aegis', [743], StackType.DURATION, 5),
        BuffType('Resistance', 'resist', [26980], StackType.DURATION, 5),
        BuffType('Stability', 'stab', [1122], StackType.INTENSITY, 25),
        BuffType('Swiftness', 'swift', [719], StackType.DURATION, 9),
        BuffType('Vigor', 'vigor', [726], StackType.DURATION, 5),

        # Ranger
        BuffType('Spotter', 'spotter', [14055], StackType.DURATION, 1, 1, 1),
        BuffType('Spirit of Frost', 'spirit_of_frost', [12544, 50421], StackType.DURATION, 1, 1, 2),
        BuffType('Sun Spirit', 'sun_spirit', [12540, 50413], StackType.DURATION, 1, 1, 2),
        BuffType('Stone Spirit', 'stone_spirit', [12547, 50415], StackType.DURATION, 1),
        BuffType('Storm Spirit', 'storm_spirit', [12549, 50381], StackType.DURATION, 1, 1, 2),
        BuffType('Glyph of Empowerment', 'glyph_of_empowerment', [31803], StackType.DURATION, 1, 1, 1),

        # Warrior
        BuffType('Empower Allies', 'empower_allies', [14222], StackType.DURATION, 1, 1, 1),
        BuffType('Banner of Strength', 'banner_strength', [14417], StackType.DURATION, 1, 1, 2),
        BuffType('Banner of Discipline', 'banner_discipline', [14449], StackType.DURATION, 1, 1, 2),
        BuffType('Banner of Tactics', 'banner_tactics', [14450], StackType.DURATION, 1, 1, 2),
        BuffType('Banner of Defence', 'banner_defence', [14543], StackType.DURATION, 1, 1, 2),

        # Revenant
        BuffType('Assassin''s Presence', 'assassins_presence', [26854], StackType.DURATION, 1, 1, 1),
        BuffType('Naturalistic Resonance', 'naturalistic_resonance', [29379], StackType.DURATION, 1, 150, 2),

        # Engineer
        BuffType('Pinpoint Distribution', 'pinpoint_distribution', [38333], StackType.DURATION, 1, 1, 2),

        # Elementalist
        BuffType('Soothing Mist', 'soothing_mist', [5587], StackType.DURATION, 1, 1, 5),

        # Necro
        BuffType('Vampiric Presence', 'vampiric_presence', [30285], StackType.DURATION, 1, 1, 1),
    
        # Thief
        BuffType('Lotus Training', 'lotus_training', [32200], StackType.DURATION, 1),
        BuffType('Lead Attacks', 'lead_attacks', [34659], StackType.INTENSITY, 15),
    
        # Guardian
        BuffType('Strength in Numbers','strength_in_numbers',[13796],StackType.DURATION, 1, 1, 1)
    
    #Future boon ids
    #Aegis - 743
    ]

BUFFS = { buff.name: buff for buff in BUFF_TYPES }
BUFF_TABS = [
    {
        'name': 'Overview',
        'order': [
            'might',
            'fury',
            'quickness',
            'alacrity',
        ],
    },
    {
        'name': 'Boons',
        'order': [
            'might',
            'fury',
            'quickness',
            'alacrity',
            'retaliation',
            'protection',
            'aegis',
            'regen',
            'swift',
            'vigor',
            'resist',
            'stab',
        ],
    },
    {
        'name': 'Offensive Buffs',
        'order': [
            'spirit_of_frost',
            'sun_spirit',
            'spotter',
            'banner_strength',
            'banner_discipline',
            'empower_allies',
            'glyph_of_empowerment',
            'assassins_presence',
            'pinpoint_distribution',
        ],
    },
    {
        'name': 'Supportive Buffs',
        'order': [
            'stone_spirit',
            'banner_tactics',
            'banner_defence',
            'storm_spirit',
            'naturalistic_resonance',
            'soothing_mist',
            'vampiric_presence',
            'strength_in_numbers',
        ],
    },
    {
        'name': 'All buffs', # XXX For now; delete when support for tabs arrives
        'order': [
            'might',
            'fury',
            'quickness',
            'alacrity',
            'protection',
            'retaliation',
            'regen',
            'spotter',
            'glyph_of_empowerment',
            'gotl',
            'spirit_of_frost',
            'sun_spirit',
            'stone_spirit',
            'storm_spirit',
            'empower_allies',
            'banner_strength',
            'banner_discipline',
            'banner_tactics',
            'banner_defence',
            'assassins_presence',
            'naturalistic_resonance',
            'pinpoint_distribution',
            'soothing_mist',
            'vampiric_presence',
            'strength_in_numbers',
        ],
    },
]

class BuffTrackIntensity:
    def __init__(self, buff_type, dst_instid, src_instids, encounter_start, encounter_end):
        self.buff_type = buff_type
        self.dst_instid = dst_instid
        self.stack_durations = []
        self.current_time = encounter_start
        
        self.src_trackers = {}
        for src in src_instids:
            self.src_trackers[src] = [src, 0, 0]
        
        self.data = []
                
    def apply_change(self, time, new_count, src_instid):
        tracker = self.src_trackers[src_instid]
        if tracker[1] > 0:
            duration = time - tracker[2]
            if duration > 0:
                self.data.append([tracker[2], duration, self.buff_type.code, src_instid, self.dst_instid, tracker[1]])
        tracker[1] = new_count 
        tracker[2] = time

    def add_event(self, event):
        if event.time != self.current_time:
            self.simulate_to_time(event.time)

        if event.is_buffremove:
            self.clear(event.time)
        elif len(self.stack_durations) < self.buff_type.capacity:
            end_time = event.time + event.value;
            self.stack_durations.append([end_time, event.ult_src_instid])
            self.stack_durations.sort()
            self.apply_change(event.time, self.src_trackers[event.ult_src_instid][1] + 1, event.ult_src_instid)
        elif self.stack_durations[0][0] < event.time + event.value:
            old_src = self.stack_durations[0][1]
            if old_src != event.ult_src_instid:
                self.apply_change(event.time, self.src_trackers[old_src][1] - 1, old_src)
                self.apply_change(event.time, self.src_trackers[event.ult_src_instid][1] + 1, event.ult_src_instid)
            end_time = event.time + event.value;
            self.stack_durations[0] = [end_time, event.ult_src_instid]
            self.stack_durations.sort()            

    def clear(self, time):
        if len(self.stack_durations) > 0:
            self.stack_durations = []
            for x in self.src_trackers:
                self.apply_change(time, 0, x)
                                  
    def simulate_to_time(self, new_time):
        while (len(self.stack_durations) > 0) and (self.stack_durations[0][0] <= new_time):
            self.apply_change(self.stack_durations[0][0], self.src_trackers[self.stack_durations[0][1]][1] - 1, self.stack_durations[0][1])
            del self.stack_durations[0]
        self.current_time = new_time
                
    def end_track(self, time):
        end_time = int(time)
        self.simulate_to_time(end_time)
        self.clear(time)
            
class BuffTrackDuration:
    def __init__(self, buff_type, dst_instid, encounter_start, encounter_end):
        self.buff_type = buff_type
        self.dst_instid = dst_instid
        self.stack_durations = []
        self.data = []
        self.current_time = encounter_start
        self.current_src = -1
        self.stack_start = encounter_start

    def apply_change(self, time):
        duration = time - self.stack_start
        if duration > 0:
            self.data.append([self.stack_start, duration, self.buff_type.code, self.current_src, self.dst_instid, 1])
        
    def add_event(self, event):
        if event.time != self.current_time:
            self.simulate(event.time - self.current_time)

        if event.is_buffremove:
            if len(self.stack_durations) > 0:
                self.stack_durations = []
                self.apply_change(event.time)
                self.current_src = -1
        elif len(self.stack_durations) < self.buff_type.capacity:
            self.stack_durations.append([event.value, event.ult_src_instid])
            if len(self.stack_durations) == 1:
                self.stack_start = event.time
                self.current_src = event.ult_src_instid
            else:
                self.stack_durations.sort()
                if self.stack_durations[0][1] != self.current_src:
                    self.apply_change(event.time)
                    self.current_src = self.stack_durations[0][1]
                    self.stack_start = event.time                
        elif self.stack_durations[0][0] < event.value:
            self.stack_durations[0] = [event.value, event.ult_src_instid]
            self.stack_durations.sort()
            if self.stack_durations[0][1] != self.current_src:
                self.apply_change(event.time)
                self.current_src = self.stack_durations[0][1]
                self.stack_start = event.time                

    def simulate(self, delta_time):
        remaining_delta = delta_time
        while len(self.stack_durations) > 0 and self.stack_durations[0][0] <= remaining_delta:
            self.current_time += self.stack_durations[0][0]
            remaining_delta -= self.stack_durations[0][0]
            del self.stack_durations[0]
            if len(self.stack_durations) == 0 or self.stack_durations[0][1] != self.current_src:
                self.apply_change(self.current_time)
                if len(self.stack_durations) == 0:
                    self.current_src = -1
                else:
                    self.current_src = self.stack_durations[0][1]
                self.stack_start = self.current_time                

        self.current_time += remaining_delta
        if len(self.stack_durations) > 0:
            self.stack_durations[0][0] -= remaining_delta

    def end_track(self, time):
        end_time = int(time)
        self.simulate(end_time - self.current_time)
        if len(self.stack_durations) > 0:
            self.apply_change(end_time)
            
class BuffPreprocessor:

    def process_events(self, start_time, end_time, skills, players, player_events):
        def process_buff_events(buff_type, buff_events, raw_buff_data):
            for player in list(players.index):
                relevent_events = buff_events[buff_events['dst_instid'] == player]

                agent_start_time = self.get_time(player_events[player_events['src_instid'] == player], parser.StateChange.SPAWN, start_time)
                agent_end_time = self.get_time(player_events[player_events['src_instid'] == player], parser.StateChange.DESPAWN, end_time)
                if len(relevent_events) > 0:
                    if relevent_events.time.min() < agent_start_time:
                        agent_start_time = start_time
                    if relevent_events.time.max() > agent_end_time:
                        agent_end_time = end_time

                if (buff_type.stacking == StackType.INTENSITY):
                    bufftrack = BuffTrackIntensity(BUFFS[buff_type.name], player, relevent_events['ult_src_instid'].drop_duplicates().tolist(), agent_start_time, agent_end_time)
                else:
                    bufftrack = BuffTrackDuration(BUFFS[buff_type.name], player, agent_start_time, agent_end_time)

                for event in relevent_events.itertuples():
                    bufftrack.add_event(event)
                bufftrack.end_track(agent_end_time)

                raw_buff_data = raw_buff_data + bufftrack.data
            return raw_buff_data
       
        # Filter out state change and cancellation events
        not_cancel_events = player_events[(player_events.state_change == parser.StateChange.NORMAL)
                                        & (player_events.is_activation < parser.Activation.CANCEL_FIRE)
                                        & player_events.dst_instid.isin(players.index)]

        # Extract out the buff events
        status_remove_groups = not_cancel_events.groupby('is_buffremove')
        if 0 in status_remove_groups.indices:
            not_statusremove_events = status_remove_groups.get_group(0)
        else:
            not_statusremove_events = not_cancel_events[not_cancel_events.is_buffremove == 0]
            
        #not_statusremove_events = not_cancel_events[not_cancel_events.is_buffremove == 0]
        apply_events = not_statusremove_events[(not_statusremove_events.buff != 0)
                                             & (not_statusremove_events.value != 0)]
        buff_events = apply_events[['skillid', 'time', 'value', 'overstack_value', 'is_buffremove', 'dst_instid', 'ult_src_instid']]

        # Extract out buff removal events
        if 1 in status_remove_groups.indices:
            statusremove_events = status_remove_groups.get_group(1)
        else:
            statusremove_events = not_cancel_events[not_cancel_events.is_buffremove == 1]
        #statusremove_events = not_cancel_events[not_cancel_events.is_buffremove == 1]
        buffremove_events = statusremove_events[['skillid', 'time', 'value', 'overstack_value', 'is_buffremove', 'dst_instid', 'ult_src_instid']]

        # Combine buff application and removal events
        buff_update_events = pd.concat([buff_events, buffremove_events]).sort_values('time')

        # Add in skill ids for ease of processing
        buff_update_events[['time', 'value']] = buff_update_events[['time', 'value']].apply(pd.to_numeric)

        raw_buff_data = []

        groups = buff_update_events.groupby('skillid')

        remaining_buff_types = list(BUFF_TYPES)
        for skillid, buff_events in groups:

            relevant_buff_types = list(filter(lambda a: skillid in a.skillid, remaining_buff_types))
            if not relevant_buff_types:
                continue
            
            buff_type = relevant_buff_types[0]
            remaining_buff_types.remove(buff_type)
            raw_buff_data = process_buff_events(buff_type, buff_events, raw_buff_data)

        buff_data = pd.DataFrame(columns = ['time', 'duration', 'buff', 'src_instid', 'dst_instid', 'stacks'], data = raw_buff_data)
        buff_data.fillna(0, inplace=True)
        buff_data[['time', 'duration', 'src_instid', 'dst_instid', 'stacks']] = buff_data[['time', 'duration', 'src_instid', 'dst_instid', 'stacks']].apply(pd.to_numeric)
        return buff_data;
    
    #format: time, duration, buff_type, src, dst, stacks 
    
    def get_time(self, player_events, state, start_time):
        event = player_events[player_events['state_change'] == state]
        if len(event) > 0:
            return event.iloc[0]['time']
        return start_time
        
