from enum import IntEnum
from evtcparser import *
import pandas as pd
import numpy as np

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

class Analyser:
    def _categorise_agents(self, agents):
        agents['archetype'] = 1 # POWER
        agents.loc[agents.condition >= 7, 'archetype'] = 2  # CONDI
        agents.loc[agents.toughness >= 7, 'archetype'] = 3  # TANK
        agents.loc[agents.healing >= 7, 'archetype'] = 4    # HEAL

    def __init__(self, encounter):
        self.encounter = encounter
        #self.time = encounter.ended_at - encounter.started_at

        # ultimate source (e.g. if necro minion attacks, the necro himself)
        events = encounter.events

        self._categorise_agents(agents)

        events['ult_src_instid'] = events.src_master_instid.where(events.src_master_instid != 0, events.src_instid)

        aware_as_src = events.groupby('ult_src_instid')['time']
        aware_as_dst = events.groupby('dst_instid')['time'] # XXX necessary to also include minions for destination awareness detection?
        first_aware_as_src = aware_as_src.first()
        last_aware_as_src = aware_as_src.last()
        first_aware_as_dst = aware_as_dst.first()
        last_aware_as_dst = aware_as_dst.last()
        first_aware = pd.DataFrame([first_aware_as_src, first_aware_as_dst]).min().astype(np.uint64)
        last_aware = pd.DataFrame([last_aware_as_src, last_aware_as_dst]).max().astype(np.uint64)
        self.agents = encounter.agents.assign(first_aware=first_aware, last_aware=last_aware)
        self.encounter_start = first_aware.min()
        self.encounter_end = last_aware.max()

        self.players = self.agents[self.agents.party != 0]
        player_events = events.join(self.players, how='right', on='ult_src_instid')

        grouped_events = player_events.groupby([events.buff != 0, events.state_change == parser.StateChange.NORMAL, events.buff_dmg > 0])
        condi_damage_by_player = grouped_events.get_group((True, True, True)).groupby('ult_src_instid')
        direct_damage_by_player = grouped_events.get_group((False, True, False)).groupby('ult_src_instid')
        self.damage = self.players.assign(
                condi = condi_damage_by_player['buff_dmg'].sum(),
                direct = direct_damage_by_player['value'].sum(),
            )

        self.key_target_ids = {encounter.area_id}

