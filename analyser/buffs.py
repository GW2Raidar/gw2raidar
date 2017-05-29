from enum import IntEnum
from evtcparser import *
import pandas as pd
import numpy as np

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
        self.buff_type = buff_type
        self.stack_end_times = []
        self.start_time = encounter_start
        self.data = np.array([np.arange(1)] * 4).T
        self.current_time = 0

    def add_event(self, event):
        event_time = int(event.time)
        if event_time != self.current_time:
            self.simulate_to_time(event_time)

        if event.is_buffremove:
            if len(self.stack_end_times) > 0:
                self.stack_end_times = []
                self.record_event(event_time, 0, 1)
        elif len(self.stack_end_times) < self.buff_type.capacity:
            self.stack_end_times += [event_time + event.value]
            self.stack_end_times.sort()
            self.record_event(event_time, len(self.stack_end_times), 0)
        elif (self.stack_end_times[0] < event_time + event.value):
            self.stack_end_times[0] = event_time + event.value
            self.stack_end_times.sort()

    def simulate_to_time(self, new_time):
        while len(self.stack_end_times) > 0 and self.stack_end_times[0] <= new_time:
            self.record_event(self.stack_end_times[0], len(self.stack_end_times) - 1, 0)
            self.stack_end_times.remove(self.stack_end_times[0])
        self.current_time = new_time

    def end_track(self, time):
        end_time = int(time)
        self.simulate_to_time(end_time)
        if self.data[-1][0] != end_time:
            self.record_event(end_time, len(self.stack_end_times), 0)
            
    def record_event(self, new_time, stacks, stripped):
        if self.data[-1][0] == new_time:
            self.data[-1][1] = stacks
            self.data[-1][2] = max(self.data[-1][2], stripped)
        else:
            self.data[-1][3] = new_time - self.data[-1][0]
            self.data = np.append(self.data, [[new_time, stacks, stripped, 0]], axis=0)

class BuffTrackDuration:
    def __init__(self, buff_type, encounter_start, encounter_end):
        self.buff_type = buff_type
        self.stack_durations = np.array([np.arange(0)]).T
        self.start_time = encounter_start
        self.data = np.array([np.arange(1)] * 4).T
        self.current_time = 0

    def add_event(self, event):
        event_time = int(event.time)
        if event_time != self.current_time:
            self.simulate(event_time - self.current_time)

        if event.is_buffremove:
            if self.stack_durations.size > 0:
                self.stack_durations = np.array([np.arange(0)]).T
                self.record_event(event_time, 0, 1)
        elif self.stack_durations.size < self.buff_type.capacity:
            if self.stack_durations.size == 0:
                self.record_event(event_time, 1, 0)
            self.stack_durations = np.append(self.stack_durations, [event.value])
            self.stack_durations.sort()
        elif (self.stack_durations[0] < event.value):
            self.stack_durations[0] = event.value
            self.stack_durations.sort()

    def simulate(self, delta_time):
        remaining_delta = delta_time
        while self.stack_durations.size > 0 and self.stack_durations[0] <= remaining_delta:
            if self.stack_durations.size == 1:
                self.record_event(int(self.stack_durations[0] + self.current_time), 0, 0)
            remaining_delta -= self.stack_durations[0]
            self.stack_durations = np.delete(self.stack_durations, 0)

        self.current_time += delta_time
        if self.stack_durations.size > 0:
            self.stack_durations[0] -= remaining_delta

    def end_track(self, time):
        end_time = int(time)
        self.simulate(end_time - self.current_time)
        if self.data[-1][0] != end_time:
            self.record_event(end_time, self.stack_durations.size > 0, 0)
            
    def record_event(self, new_time, stacks, stripped):
        if self.data[-1][0] == new_time:
            self.data[-1][1] = stacks
            self.data[-1][2] = max(self.data[-1][2], stripped)
        else:
            self.data[-1][3] = new_time - self.data[-1][0]
            self.data = np.append(self.data, [[new_time, stacks, stripped, 0]], axis=0)

class BuffPreprocessor:

    def process_events(self, start_time, end_time, skills, players, player_events):
        # Filter out state change and cancellation events
        not_state_change_events = player_events[player_events.state_change == parser.StateChange.NORMAL]
        not_cancel_events = not_state_change_events[not_state_change_events.is_activation < parser.Activation.CANCEL_FIRE]

        # Extract out the buff events
        not_statusremove_events = not_cancel_events[not_cancel_events.is_buffremove == 0]
        status_events = not_statusremove_events[not_statusremove_events.buff != 0]
        apply_events = status_events[status_events.value != 0]
        buff_events = (apply_events[apply_events.dst_instid.isin(players.index)]
                [['skillid', 'time', 'value', 'overstack_value', 'is_buffremove', 'dst_instid']])

        # Extract out buff removal events
        statusremove_events = not_cancel_events[not_cancel_events.is_buffremove != 0]
        buffremove_events = (statusremove_events[statusremove_events.dst_instid.isin(list(players.index))]
                [['skillid', 'time', 'value', 'overstack_value', 'is_buffremove', 'dst_instid']])

        # Combine buff application and removal events
        buff_update_events = pd.concat([buff_events, buffremove_events]).sort_values('time')

        # Add in skill ids for ease of processing
        buff_update_events = buff_update_events.join(skills, how='inner', on='skillid').sort_values(by='time');

        raw_buff_data = np.array([]).reshape(0,6)
        for buff_type in BUFF_TYPES: 
            buff_events = buff_update_events[buff_update_events['name'] == buff_type.name]
            for player in list(players.index):
                if (buff_type.stacking == StackType.INTENSITY):
                    bufftrack = BuffTrackIntensity(BUFFS[buff_type.name], start_time, end_time)
                else:
                    bufftrack = BuffTrackDuration(BUFFS[buff_type.name], start_time, end_time)
                relevent_events = buff_events[buff_events['dst_instid'] == player]
                for event in relevent_events.itertuples():
                    bufftrack.add_event(event)
                bufftrack.end_track(end_time)

                track_data = bufftrack.data
                track_data = np.c_[[buff_type.code] * track_data.shape[0], [player] * track_data.shape[0], track_data]
                raw_buff_data = np.r_[raw_buff_data, track_data]

        buff_data = pd.DataFrame(columns = ['buff', 'player', 'time', 'stacks', 'stripped', 'duration'], data = raw_buff_data)
        buff_data[['player', 'time', 'stacks', 'duration']] = buff_data[['player', 'time', 'stacks', 'duration']].apply(pd.to_numeric)
        return buff_data;
