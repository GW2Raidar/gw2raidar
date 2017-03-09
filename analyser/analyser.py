from enum import IntEnum
from evtcparser import *
import pandas as pd
import numpy as np
from functools import reduce

# DEBUG
from sys import exit


class BasicMetric:
    def __init__(self, data):
        self.data = data

    def __iter__(self):
        return iter(self.data.items())

class StructuredMetric:
    def __iter__(self):
        return filter(lambda a: a[0][0] != '_', vars(self).items())

class SkillDamageMetric(BasicMetric):
    def add_damage(self, skill_name, damage):
        self.data[skill_name] = self.data.get(skill_name, 0) + damage

class TeamDPSMetric(StructuredMetric):
    def __init__(self, player_dps):
        self.player_dps = player_dps
        self.total_damage = sum(map(lambda a: a.total_damage, player_dps.values()))
        self.total_condi = sum(map(lambda a: a.total_condi, player_dps.values()))
        self.total_power = sum(map(lambda a: a.total_power, player_dps.values()))
        self.dps = sum(map(lambda a: a.dps, player_dps.values()))
        self.dps_condi = sum(map(lambda a: a.dps_condi, player_dps.values()))
        self.dps_power = sum(map(lambda a: a.dps_power, player_dps.values()))

class PlayerDPSMetric(StructuredMetric):
    def __init__(self):
        self.total_damage = 0
        self.total_condi = 0
        self.total_power = 0
        self.total_skill_damage = SkillDamageMetric({})

        self._hits = 0
        self._crits = 0

        self.dps = None
        self.dps_condi = None
        self.dps_power = None
        self.crit_rate = None

    def value(self):
        return self.dps

    def add_damage(self, skill_name, target_inst_id, damage, is_condi, is_crit):
        self.total_damage += damage
        self.total_skill_damage.add_damage(skill_name, damage)
        if is_condi:
            self.total_condi += damage
        else:
            self.total_power += damage
            self._hits += 1
            if is_crit:
                self._crits += 1

    def end(self, time):
        self.dps = self.total_damage / time
        self.dps_condi = self.total_condi / time
        self.dps_power = self.total_power / time
        self.dps = self.total_damage / time

        if self._hits > 0:
            self.crit_rate = self._crits / self._hits

class LogType(IntEnum):
    UNKNOWN = 0
    POWER = 1
    CONDI = 2
    BUFF = 3
    HEAL = 4


class Boss:
    def __init__(self, name, profs, invuln=None):
        self.name = name
        self.profs = profs
        self.invuln = invuln


EVENT_TYPES = {
        (True,  True,  True): 'condi',
        (True,  True, False): 'buff',
        (True,  False,  True): '?', #'weird_condi',
        (True,  False, False): '??', #'weird_buff',
        (False, True,  True): '???', #'normal_uncondi',
        (False, True, False): 'skill', #'normal_unbuff',
        (False, False,  True): 'log_start', #'weird_uncondi',
        (False, False, False): 'state_change', #'weird_unbuff',
    }

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
BOSSES = { boss.profs[0]: boss for boss in BOSS_ARRAY }

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

class BuffTrack:
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
        while len(self.stack_end_times) > 0 and self.stack_end_times[0] < new_time:
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
        
class Analyser:
    def __init__(self, encounter):
        self.encounter = encounter

        # ultimate source (e.g. if necro minion attacks, the necro himself)
        events = encounter.events
        agents = encounter.agents

        events['ult_src_instid'] = events.src_master_instid.where(events.src_master_instid != 0, events.src_instid)

        # awareness is defined as interval between first skill use
        # and last skill use, on (dst) or by (src) an agent
        # (e.g. casting a spell on VG makes it aware;
        # being hit by VG's teleport also makes it aware)
        aware_as_src = events.groupby('ult_src_instid')['time']
        aware_as_dst = events.groupby('dst_instid')['time'] # XXX necessary to also include minions for destination awareness detection?
        first_aware_as_src = aware_as_src.first()
        last_aware_as_src = aware_as_src.last()
        first_aware_as_dst = aware_as_dst.first()
        last_aware_as_dst = aware_as_dst.last()
        first_aware = pd.DataFrame([first_aware_as_src, first_aware_as_dst]).min().astype(np.uint64)
        last_aware = pd.DataFrame([last_aware_as_src, last_aware_as_dst]).max().astype(np.uint64)
        agents = agents.assign(first_aware=first_aware, last_aware=last_aware)

        # get all the bosses; the encounter starts when any boss
        # is first aware, and ends when the last boss awareness ends
        boss = BOSSES[encounter.area_id]
        boss_agents = agents[agents.prof.isin(boss.profs)]
        encounter_start = boss_agents.first_aware.min()
        encounter_end = boss_agents.last_aware.max()

        # player archetypes
        agents['archetype'] = 0
        agents.loc[agents.party != 0, 'archetype'] = 1     # POWER
        agents.loc[agents.condition >= 7, 'archetype'] = 2  # CONDI
        agents.loc[agents.toughness >= 7, 'archetype'] = 3  # TANK
        agents.loc[agents.healing >= 7, 'archetype'] = 4    # HEAL

        # get player events (players are the only agents in a party)
        players = agents[agents.party != 0]
        # TODO for speed we can convert join into restriction
        # (join gives more context for debugging)
        # For most of the metrics, we only care about the events
        # originating from players, that happen during the encounter;
        # then slice those player events based on DeltaConnected's
        # description into different sets.
        player_events = events.join(players[['name', 'account']], how='right', on='ult_src_instid').sort_values(by='time')
        player_events = player_events[player_events.time.between(encounter_start, encounter_end)]

        # most of the events below need to not be state change events, even
        # though DeltaConnected does not mention it
        not_state_change_events = player_events[player_events.state_change == parser.StateChange.NORMAL]

        # DeltaConnected:
        # > on cbtitem.is_activation == cancel_fire or cancel_cancel, value will be the ms duration of the approximate channel.
        cancel_fire_events = not_state_change_events[not_state_change_events.is_activation == parser.Activation.CANCEL_FIRE]
        cancel_cancel_events = not_state_change_events[not_state_change_events.is_activation == parser.Activation.CANCEL_CANCEL]
        not_cancel_events = not_state_change_events[not_state_change_events.is_activation < parser.Activation.CANCEL_FIRE]

        # DeltaConnected:
        # > on cbtitem.is_buffremove, value will be the duration removed (negative) equal to the sum of all stacks.
        statusremove_events = not_cancel_events[not_cancel_events.is_buffremove != 0]
        not_statusremove_events = not_cancel_events[not_cancel_events.is_buffremove == 0]

        # DeltaConnected:
        # > if they are all 0, it will be a buff application (!cbtitem.is_buffremove && cbtitem.is_buff) or physical hit (!cbtitem.is_buff).
        status_events = not_statusremove_events[not_statusremove_events.buff != 0]

        # DeltaConnected:
        # > on physical, cbtitem.value will be the damage done (positive).
        # > on physical, cbtitem.result will be the result of the attack.
        hit_events = not_statusremove_events[not_statusremove_events.buff == 0]

        # DeltaConnected:
        # > on buff && !cbtitem.buff_dmg, cbtitem.value will be the millisecond duration.
        # > on buff && !cbtitem.buff_dmg, cbtitem.overstack_value will be the current smallest stack duration in ms if over the buff's stack cap.
        apply_events = status_events[status_events.value != 0]

        # DeltaConnected:
        # > on buff && !cbtitem.value, cbtitem.buff_dmg will be the approximate damage done by the buff.
        condi_events = status_events[status_events.value == 0]

        # find out large periods when no boss is being hit by players' skills
        # (phase times)
        gap_events = None
        time = encounter_end - encounter_start
        if boss.invuln:
            hit_gap_duration = hit_events.join(boss_agents['prof'], on='dst_instid', rsuffix='_dst', how='inner')['time'].diff()
            gap_events = hit_events[['time']].assign(hit_gap_duration=hit_gap_duration)
            gap_events = gap_events[gap_events.hit_gap_duration > boss.invuln]
            gap_events['start'] = (gap_events.time - gap_events.hit_gap_duration).astype(np.uint64)
            time -= gap_events['hit_gap_duration'].sum()

        # get only events that happened while the boss was not invulnerable
        def non_gap(events):
            if gap_events is None or gap_events.empty:
                return events
            else:
                in_gap = reduce(lambda x, y: x | y, [events.time.between(gap.start, gap.time) for gap in gap_events.itertuples()])
                return events[-in_gap]

        # damage sums
        direct_damage_to_boss_events = non_gap(hit_events.join(boss_agents['prof'], on='dst_instid', rsuffix='_dst', how='inner'))
        condi_damage_to_boss_events = non_gap(condi_events.join(boss_agents['prof'], on='dst_instid', rsuffix='_dst', how='inner'))
        
        direct_damage_to_boss_events_by_player = direct_damage_to_boss_events.groupby('ult_src_instid')
        condi_damage_to_boss_events_by_player = condi_damage_to_boss_events.groupby('ult_src_instid')

        condi_damage_by_player = non_gap(condi_events).groupby('ult_src_instid')['buff_dmg'].sum()
        direct_damage_by_player = non_gap(hit_events).groupby('ult_src_instid')['value'].sum()
        condi_damage_by_player_to_boss = condi_damage_to_boss_events_by_player['buff_dmg'].sum()
        direct_damage_by_player_to_boss = direct_damage_to_boss_events_by_player['value'].sum()

        # hit percentage while under special condition
        direct_damage_to_boss_count = direct_damage_to_boss_events_by_player['value'].count()

        flanking_hits_by_player_to_boss_count = direct_damage_to_boss_events[direct_damage_to_boss_events.is_flanking != 0].groupby('ult_src_instid')['value'].count()
        flanking = flanking_hits_by_player_to_boss_count / direct_damage_to_boss_count

        ninety_hits_by_player_to_boss_count = direct_damage_to_boss_events[direct_damage_to_boss_events.is_ninety != 0].groupby('ult_src_instid')['value'].count()
        ninety = ninety_hits_by_player_to_boss_count / direct_damage_to_boss_count

        moving_hits_by_player_to_boss_count = direct_damage_to_boss_events[direct_damage_to_boss_events.is_moving != 0].groupby('ult_src_instid')['value'].count()
        moving = moving_hits_by_player_to_boss_count / direct_damage_to_boss_count

        # identify the timestamp that represents the start of the log, and the
        # tick ('time') that is equivalent to it
        start_event = events[events.state_change == parser.StateChange.LOG_START]
        start_timestamp = start_event['value'][0]
        start_time = start_event['time'][0]

        # buffs (status application events from players targetting players)
        buff_events = (apply_events[apply_events.dst_instid.isin(players.index)]
                [['skillid', 'time', 'value', 'overstack_value', 'is_buffremove', 'dst_instid']])
        buffremove_events = (statusremove_events[statusremove_events.dst_instid.isin(list(players.index))]
                [['skillid', 'time', 'value', 'overstack_value', 'is_buffremove', 'dst_instid']])
        buff_update_events = pd.concat([buff_events, buffremove_events]).sort_values('time')
        buff_update_events = buff_update_events.join(encounter.skills, how='inner', on='skillid').sort_values(by='time');

        for buff_type in BUFF_TYPES:
            bufftracks = {}        
            if (buff_type.stacking == StackType.INTENSITY):
                buff_events = buff_update_events[buff_update_events['name'] == buff_type.name]
                for player in list(players.index):
                    bufftrack = BuffTrack(BUFFS[buff_type.name], encounter_start, encounter_end)
                    relevent_events = buff_events[buff_events['dst_instid'] == player]
                    for event in relevent_events.itertuples():
                        bufftrack.add_event(event)
                    bufftrack.end_track(encounter_end)
                    bufftracks[player] = bufftrack

                mean_per_player = np.array([np.arange(0)] * 2).T

                for player in list(players.index):
                    buff_data = pd.DataFrame(columns = ['time', 'stacks'], data = bufftracks[player].data)
                    diff_data = (buff_data[['time']].diff(periods=-1, axis=0)[:-1] * -1).join(buff_data[['stacks']])
                    mean_per_player = np.append(mean_per_player, 
                                                [[player, (diff_data['time'] * diff_data['stacks']).sum() / time]], axis = 0)
                mean_per_player_df = pd.DataFrame(columns = [ buff_type.code], data = mean_per_player[0:,1:],
                                                  index = mean_per_player[0:, 0])
                players = players.join(mean_per_player_df)
        
        # export analysis results

        # per player
        self.players = players.assign(
                condi = condi_damage_by_player,
                direct = direct_damage_by_player,
                condi_dps = condi_damage_by_player / time * 1000,
                direct_dps = direct_damage_by_player / time * 1000,
                condi_boss = condi_damage_by_player_to_boss,
                direct_boss = direct_damage_by_player_to_boss,
                condi_boss_dps = condi_damage_by_player_to_boss / time * 1000,
                direct_boss_dps = direct_damage_by_player_to_boss / time * 1000,
                flanking = flanking,
                ninety = ninety,
                moving = moving,
            )
        
        # per party
        self.party = {
                'direct': direct_damage_by_player.sum(),
                'condi': condi_damage_by_player.sum(),
                'direct_boss': direct_damage_by_player_to_boss.sum(),
                'condi_boss': condi_damage_by_player_to_boss.sum(),
            }

        # not player-related
        self.info = {
                'name': boss.name,
                'start': int(start_timestamp),
                'end': int(start_timestamp + int((encounter_end - start_time) / 1000)),
            }
