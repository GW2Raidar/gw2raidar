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
    SPECTRAL_IMPACT = 31875
    GHASTLY_PRISON = 31623
    HEAVY_BOMB_EXPLODE = 31596
    TANTRUM = 34479
    BLEEDING = 736
    BURNING = 737
    VOLATILE_POISON = 34387
    UNBALANCED = 34367
    CORRUPTION = 34416
    SURRENDER = 34413
    BLOOD_FUELED = 34422
    SACRIFICE = 34442
    UNSTABLE_BLOOD_MAGIC = 34450

class BossMetricAnalyser:
    def __init__(self, agents, subgroups, players, bosses, phases):
        self.agents = agents
        self.subgroups = subgroups
        self.players = players
        self.bosses = bosses
        self.phases = phases
        
    def standard_count(events):
        return len(events);

    def gather_count_stat(self, name, collector, by_player, by_phase, events, calculation = standard_count):
        def count_by_phase(collector, events, func):
            split_by_phase(collector, func, events, self.phases)        
        def count_by_player(collector, events):
            split_by_player_groups(collector, count, events, 'dst_instid', self.subgroups, self.players) 
        def count(collector, events):
            collector.add_data(name, calculation(events), int)
        
        if by_phase and by_player:
            count_by_phase(collector, events, count_by_player)
        elif by_phase:
            collector = collector.with_key(Group.SUBGROUP, "*All")
            count_by_phase(collector, events, count)
        elif by_player:
            collector = collector.with_key(Group.PHASE, "All")
            count_by_player(collector, events)
        else:
            collector = collector.with_key(Group.PHASE, "All").with_key(Group.SUBGROUP, "*All")
            count(collector, events)
    
    def gather_boss_specific_stats(self, events, collector):
        metric_collector = collector.with_key(Group.CATEGORY, "combat").with_key(Group.METRICS, "mechanics")
        if len(self.bosses[self.bosses.name == 'Vale Guardian']) != 0:
            self.gather_vg_stats(events, metric_collector)
        elif len(self.bosses[self.bosses.name == 'Gorseval the Multifarious']) != 0:
            self.gather_gorse_stats(events, metric_collector)
        elif len(self.bosses[self.bosses.name == 'Sabetha the Saboteur']) != 0:
            self.gather_sab_stats(events, metric_collector)
        elif len(self.bosses[self.bosses.name == 'Slothasor']) != 0:
            self.gather_sloth_stats(events, metric_collector)
        elif len(self.bosses[self.bosses.name == 'Matthias Gabrel']) != 0:
            self.gather_matt_stats(events, metric_collector)
           
    def gather_vg_stats(self, events, collector):
        teleport_events = events[(events.skillid == Skills.UNSTABLE_MAGIC_SPIKE) & events.dst_instid.isin(self.players.index) & (events.value > 0)]
        bullet_storm_events = events[(events.skillid == Skills.BULLET_STORM) & events.dst_instid.isin(self.players.index) & (events.value > 0)]
        self.gather_count_stat('Teleports', collector, True, False, teleport_events) 
        self.gather_count_stat('Bullets Eaten', collector, True, False, bullet_storm_events)
        self.vg_blue_guardian_invul(events, collector)
        
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
        
        collector.with_key(Group.PHASE, "All").with_key(Group.SUBGROUP, "*All").add_data('Blue Guardian Invulnerability Time', time, int)
        
    def gather_gorse_stats(self, events, collector):
        spectral_impact_events = events[(events.skillid == Skills.SPECTRAL_IMPACT) & events.dst_instid.isin(self.players.index) & (events.value > 0)]
        imprisonment_events = events[(events.skillid == Skills.GHASTLY_PRISON) & events.dst_instid.isin(self.players.index) & (events.is_buffremove == 0)]
        self.gather_count_stat('Unmitigated Spectral Impacts', collector, True, True, spectral_impact_events)
        self.gather_count_stat('Ghastly Imprisonments', collector, True, False, imprisonment_events)

    def gather_sab_stats(self, events, collector):
        bomb_explosion_events = events[(events.skillid == Skills.HEAVY_BOMB_EXPLODE) & (events.is_buffremove == 1)]
        self.gather_count_stat('Heavy Bombs Undefused', collector, False, False, bomb_explosion_events)    

    def gather_sloth_stats(self, events, collector):
        tantrum_hits = events[(events.skillid == Skills.TANTRUM) & events.dst_instid.isin(self.players.index) & (events.value > 0)]
        spores_received = events[(events.skillid == Skills.BLEEDING) & events.dst_instid.isin(self.players.index) & (events.value > 0) & (events.is_buffremove == 0)]
        spores_blocked = events[(events.skillid == Skills.BLEEDING) & events.dst_instid.isin(self.players.index) & (events.value == 0) & (events.is_buffremove == 0)]
        volatile_poison = events[(events.skillid == Skills.VOLATILE_POISON) & events.dst_instid.isin(self.players.index) & (events.buff == 1) & (events.is_buffremove == 0)]
        self.gather_count_stat('Tantrum Knockdowns', collector, True, False, tantrum_hits)
        self.gather_count_stat('Spores Received', collector, True, False, spores_received, lambda e: len(e) / 5)
        self.gather_count_stat('Spores Blocked', collector, True, False, spores_blocked, lambda e: len(e) / 5)
        self.gather_count_stat('Volatile Poison Carrier', collector, True, False, volatile_poison)
        
    def gather_matt_stats(self, events, collector):
        unbalanced_events = events[(events.skillid == Skills.UNBALANCED) & events.dst_instid.isin(self.players.index) & (events.buff == 0)]
        surrender_events = events[(events.skillid == Skills.SURRENDER) & events.dst_instid.isin(self.players.index) & (events.value > 0)]
        burning_events = events[(events.skillid == Skills.BURNING) & events.dst_instid.isin(self.players.index) & events.src_instid.isin(self.bosses.index) & (events.value > 0) & (events.buff == 1) & (events.is_buffremove == 0)]
        corrupted_events = events[(events.skillid == Skills.CORRUPTION) & events.dst_instid.isin(self.players.index) & (events.buff == 1) & (events.is_buffremove == 0)]
        blood_fueled_events = events[(events.skillid == Skills.BLOOD_FUELED) & (events.buff == 1) & (events.is_buffremove == 0)]
        sacrifice_events = events[(events.skillid == Skills.SACRIFICE) & (events.buff == 1) & (events.is_buffremove == 0)]
        profane_events = events[(events.skillid == Skills.UNSTABLE_BLOOD_MAGIC) & (events.buff == 1) & (events.is_buffremove == 0)]
        
        self.gather_count_stat('Moved While Unbalanced', collector, True, False, unbalanced_events)
        self.gather_count_stat('Surrender', collector, True, False, surrender_events)
        self.gather_count_stat('Burning Stacks Received', collector, True, True, burning_events)
        self.gather_count_stat('Corrupted', collector, True, False, corrupted_events)
        self.gather_count_stat('Matthias Shards Returned', collector, False, False, 
                               blood_fueled_events[blood_fueled_events.dst_instid.isin(self.bosses.index)])
        self.gather_count_stat('Shards Absorbed', collector, True, False, 
                               blood_fueled_events[blood_fueled_events.dst_instid.isin(self.players.index)])
        self.gather_count_stat('Sacrificed', collector, True, False, sacrifice_events)
        self.gather_count_stat('Well of the Profane Carrier', collector, True, False, profane_events)
    