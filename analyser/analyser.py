
from enum import Enum
from evtcparser import *

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

class LogType(Enum):
    UNKNOWN = 0
    POWER = 1
    CONDI = 2
    BUFF = 3
    HEAL = 4


    @staticmethod
    def of(event):
        if event.buff:
            if event.buff_dmg > 0:
                return LogType.CONDI
            else:
                return LogType.BUFF
        elif event.state_change == parser.StateChange.NORMAL:
            return LogType.POWER

        return LogType.UNKNOWN


class Analyser:
    def __init__(self, encounter):
        self.encounter = encounter
        start_time = self.encounter.events[0].time
        end_time = self.encounter.events[-1].time
        self.time = (end_time - start_time)/1000

        self.events = dict((t,[]) for t in list(LogType))
        self.agents = dict((agent.inst_id,agent) for agent in self.encounter.agents)
        self.players = filter(lambda a: a.prof.is_player(), self.encounter.agents)
        self.key_target_ids = {encounter.area_id}
        self.skill_names = dict((skill.id,skill.name) for skill in self.encounter.skills)

        for event in self.encounter.events:
            self.events[LogType.of(event)].append(event)

    def get_player_source(self, event):
        agent = self.agents.get(event.src_instid)
        if agent and agent.prof.is_player():
            return agent
        agent = self.agents.get(event.src_master_instid)
        if agent and agent.prof.is_player():
            return agent
        return None

    def compute_dps_metrics(self):
        player_dps = dict((agent.name, PlayerDPSMetric()) for agent in self.players)
        for event in self.events[LogType.CONDI]:
            player_source = self.get_player_source(event)
            if player_source != None:
                skill_name = self.skill_names[event.skill_id]
                player_dps[player_source.name].add_damage(
                    skill_name, event.dst_instid, event.buff_dmg, True, False)

        for event in self.events[LogType.POWER]:
            player_source = self.get_player_source(event)
            if player_source != None:
                skill_name = self.skill_names[event.skill_id]
                player_dps[player_source.name].add_damage(
                    skill_name, event.dst_instid, event.value, False, event.result == parser.Result.CRIT)

        for name in player_dps:
            player_dps[name].end(self.time)

        return TeamDPSMetric(player_dps)

    def compute_all_metrics(self):
        dps_metrics = self.compute_dps_metrics()
        return BasicMetric({"DPS": dps_metrics})
