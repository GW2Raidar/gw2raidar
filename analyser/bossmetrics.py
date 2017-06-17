from enum import IntEnum
from evtcparser import *
import pandas as pd
import numpy as np
from functools import reduce
from .collector import *
from .splits import *

class Skills:
    BLUE_PYLON_POWER = 31413
    BULLET_STORM = 31793
    UNSTABLE_MAGIC_SPIKE = 31392

class BossMetricAnalyser:
    def __init__(self, agents, subgroups, players, bosses):
        self.agents = agents
        self.subgroups = subgroups
        self.players = players
        self.bosses = bosses
    
    def gather_boss_specific_stats(self, events, collector):
        if len(self.bosses[self.bosses.name == 'Vale Guardian']) != 0:
            self.gather_vg_stats(events, collector)
   
    def gather_vg_stats(self, events, collector):
        self.vg_blue_guardian_invul(events, collector)
        self.vg_bullets_eaten(events, collector)
        self.vg_teleports(events, collector)
        
    def vg_teleports(self, events, collector):
        subcollector = collector.with_key(Group.CATEGORY, "combat").with_key(Group.METRICS, "mechanics").with_key(Group.PHASE, "All")
        def count_teleports(collector, events):
            collector.add_data('Teleports', len(events), int)
        
        relevent_events = events[(events.skillid == Skills.UNSTABLE_MAGIC_SPIKE) & events.dst_instid.isin(self.players.index) & (events.value > 0)]
        split_by_player_groups(subcollector, count_teleports, relevent_events, 'dst_instid', self.subgroups, self.players)
        
    def vg_bullets_eaten(self, events, collector):
        subcollector = collector.with_key(Group.CATEGORY, "combat").with_key(Group.METRICS, "mechanics").with_key(Group.PHASE, "All")
        def count_bullets_eaten(collector, events):
            collector.add_data('Bullets Eaten', len(events), int)
        relevent_events = events[(events.skillid == Skills.BULLET_STORM) & events.dst_instid.isin(self.players.index) & (events.value > 0)]
        split_by_player_groups(subcollector, count_bullets_eaten, relevent_events, 'dst_instid', self.subgroups, self.players)

    def vg_blue_guardian_invul(self, events, collector):
        relevent_events = events[(events.skillid == Skills.BLUE_PYLON_POWER) & ((events.is_buffremove == 1) | (events.is_buffremove == 0))]
        
        time = 0
        start_time = 0
        buff_up = False
        for event in relevent_events.itertuples():
            if buff_up == False & (event.is_buffremove == 0):
                buff_up = True
                start_time = event.time
            elif buff_up == True & (event.is_buffremove == 1):
                buff_up = False
                time += event.time - start_time
        
        collector.with_key(Group.CATEGORY, "combat").with_key(Group.METRICS, "mechanics").with_key(Group.PHASE, "All").with_key(Group.SUBGROUP, "*All").add_data('Blue Guardian Invulnerability Time', time, int)