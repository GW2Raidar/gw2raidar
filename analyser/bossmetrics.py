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
    SPECTRAL_DARKNESS = 31498
    HEAVY_BOMB_EXPLODE = 31596
    TANTRUM = 34479
    TOXIC_CLOUD = 34565
    BLEEDING = 736
    BURNING = 737
    VOLATILE_POISON = 34387
    UNBALANCED = 34367
    CORRUPTION = 34416
    SURRENDER = 34413
    BLOOD_FUELED = 34422
    SACRIFICE = 34442
    UNSTABLE_BLOOD_MAGIC = 34450
    DERANGEMENT = 34965
    DISPLACEMENT = 38113
    METEOR_SWARM = 38313
    SHARED_AGONY = 38049
    SPATIAL_MANIPULATION = {37611, 37642, 37673, 38074, 38302}
    PROTECT = 37813
    CLAIM = 37779
    DISPEL = 37697
    SOLDIERS_AURA = 37677

class BossMetricAnalyser:
    def __init__(self, agents, subgroups, players, bosses, phases):
        self.agents = agents
        self.subgroups = subgroups
        self.players = players
        self.bosses = bosses
        self.phases = phases

    def standard_count(events):
        return len(events);

    def generate_player_buff_times(self, events, players, skillid):
        # Get Up/Down/Death events
        events = events[(events.skillid == skillid) & (events.buff == 1)].sort_values(by='time')

        raw_data = np.array([np.arange(0, dtype=int)] * 3, dtype=int).T
        for player in list(players.index):
            data = np.array([np.arange(0)] * 2).T
            player_events = events[((events['dst_instid'] == player)&(events.is_buffremove == 0))|
                                   ((events['src_instid'] == player)&(events.is_buffremove == 1))]

            active = False
            start_time = 0
            for event in player_events.itertuples():
                if event.is_buffremove == 0 and active == False:
                    active = True
                    start_time = event.time
                elif event.is_buffremove == 1 and active == True:
                    active = False
                    data = np.append(data, [[start_time, event.time - start_time]], axis=0)

            if active == True:
                data = np.append(data, [[start_time, encounter_end - start_time]], axis=0)

            data = np.c_[[player] * data.shape[0], data]
            raw_data = np.r_[raw_data, data]

        return pd.DataFrame(columns = ['player', 'time', 'duration'], data = raw_data)

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
        self.end_time = events.time.max()
        self.start_time = events.time.min()
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
        elif len(self.bosses[self.bosses.name == 'Xera']) != 0:
            self.gather_xera_stats(events, metric_collector)
        elif len(self.bosses[self.bosses.name == 'Cairn the Indomitable']) != 0:
            self.gather_cairn_stats(events, metric_collector)
        elif len(self.bosses[self.bosses.name == 'Mursaat Overseer']) != 0:
            self.gather_mursaat_overseer_stats(events, metric_collector)

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
        self.gorse_spectral_darkness_time('Spectral Darkness', collector, events)

    def gorse_spectral_darkness_time(self, name, collector, events):
        times = self.generate_player_buff_times(events, self.players, Skills.SPECTRAL_DARKNESS)
        collector = collector.with_key(Group.PHASE, "All")
        def count(collector, times):
            collector.add_data(name, times['duration'].sum(), int)
        split_by_player_groups(collector, count, times, 'player', self.subgroups, self.players)

    def gather_sab_stats(self, events, collector):
        bomb_explosion_events = events[(events.skillid == Skills.HEAVY_BOMB_EXPLODE) & (events.is_buffremove == 1)]
        self.gather_count_stat('Heavy Bombs Undefused', collector, False, False, bomb_explosion_events)

    def gather_sloth_stats(self, events, collector):
        tantrum_hits = events[(events.skillid == Skills.TANTRUM) & events.dst_instid.isin(self.players.index) & (events.value > 0)]
        spores_received = events[(events.skillid == Skills.BLEEDING) & events.dst_instid.isin(self.players.index) & (events.value > 0) & (events.is_buffremove == 0)]
        spores_blocked = events[(events.skillid == Skills.BLEEDING) & events.dst_instid.isin(self.players.index) & (events.value == 0) & (events.is_buffremove == 0)]
        volatile_poison = events[(events.skillid == Skills.VOLATILE_POISON) & events.dst_instid.isin(self.players.index) & (events.buff == 1) & (events.is_buffremove == 0)]
        toxic_cloud = events[(events.skillid == Skills.TOXIC_CLOUD) & events.dst_instid.isin(self.players.index) & (events.value == 0)]                                                                                                                                          
        self.gather_count_stat('Tantrum Knockdowns', collector, True, False, tantrum_hits)
        self.gather_count_stat('Spores Received', collector, True, False, spores_received, lambda e: len(e) / 5)
        self.gather_count_stat('Spores Blocked', collector, True, False, spores_blocked, lambda e: len(e) / 5)
        self.gather_count_stat('Volatile Poison Carrier', collector, True, False, volatile_poison)
        self.gather_count_stat('Toxic Cloud Breathed', collector, True, False, toxic_cloud)                             

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

    def gather_xera_stats(self, events, collector):
        derangement_events = events[(events.skillid == Skills.DERANGEMENT) & (events.buff == 1) & ((events.dst_instid.isin(self.players.index) & (events.is_buffremove == 0))|(events.src_instid.isin(self.players.index) & (events.is_buffremove == 1)))]
        self.gather_count_stat('Derangement', collector, True, False, derangement_events[derangement_events.is_buffremove == 0])
        #self.xera_derangement_max_stacks('Peak Derangement', collector, derangement_events)

    def xera_derangement_max_stacks(self, name, collector, events):
        events = events.sort_values(by='time')

        raw_data = np.array([np.arange(0, dtype=int)] * 2, dtype=int).T
        for player in list(self.players.index):
            player_events = events[((events['dst_instid'] == player)&(events.is_buffremove == 0))|
                                   ((events['src_instid'] == player)&(events.is_buffremove == 1))]

            max_stacks = 0
            stacks = 0
            for event in player_events.itertuples():
                if event.is_buffremove == 0:
                    stacks = stacks + 1
                elif event.is_buffremove == 1:
                    print(str(event.time - self.start_time) + " - " + str(stacks))
                    if stacks > max_stacks:
                        max_stacks = stacks
                    stacks = max(stacks - 8, 0)

            print(stacks)
            if stacks > max_stacks:
                max_stacks = stacks
            raw_data = np.append(raw_data, [[player, max_stacks]], axis=0)

        data = pd.DataFrame(columns = ['player', 'max_stacks'], data = raw_data)

        collector = collector.with_key(Group.PHASE, "All")
        def max_stacks(collector, data):
            collector.add_data(name, data['max_stacks'].max(), int)
        split_by_player_groups(collector, max_stacks, data, 'player', self.subgroups, self.players)
    
    def gather_cairn_stats(self, events, collector):
        displacement_events = events[(events.skillid == Skills.DISPLACEMENT) & events.dst_instid.isin(self.players.index) & (events.value > 0)]
        meteor_swarm_events = events[(events.skillid == Skills.METEOR_SWARM) & events.dst_instid.isin(self.players.index) & (events.value > 0)]
        spatial_manipulation_events = events[(events.skillid.isin(Skills.SPATIAL_MANIPULATION)) & events.dst_instid.isin(self.players.index) & (events.value > 0)]
        shared_agony_events = events[(events.skillid == Skills.SHARED_AGONY) & events.dst_instid.isin(self.players.index) & (events.buff == 1) & (events.is_buffremove == 0)] 
        self.gather_count_stat('Displacement', collector, True, False, displacement_events)
        self.gather_count_stat('Meteor Swarm', collector, True, False, meteor_swarm_events)
        self.gather_count_stat('Spatial Manipulation', collector, True, False, spatial_manipulation_events)
        self.gather_count_stat('Shared Agony', collector, True, False, shared_agony_events)

        
    def gather_mursaat_overseer_stats(self, events, collector):
        protect_events = events[(events.skillid == Skills.PROTECT) & events.dst_instid.isin(self.players.index) & (events.buff == 1) & (events.is_buffremove == 0)]
        claim_events = events[(events.skillid == Skills.CLAIM) & events.dst_instid.isin(self.players.index) & (events.buff == 1) & (events.is_buffremove == 0)]
        dispel_events = events[(events.skillid == Skills.DISPEL) & events.dst_instid.isin(self.players.index) & (events.buff == 1) & (events.is_buffremove == 0)]
        soldiers_aura_events = events[(events.skillid == Skills.SOLDIERS_AURA) & events.dst_instid.isin(self.players.index) & (events.value > 0)]
        soldiers = events[(events.skillid == Skills.SOLDIERS_AURA)].groupby('src_instid').first()
        
        self.gather_count_stat('Protect', collector, True, False, protect_events)
        self.gather_count_stat('Claim', collector, True, False, claim_events)
        self.gather_count_stat('Dispel', collector, True, False, dispel_events)
        self.gather_count_stat('Soldiers', collector, False, False, soldiers)
        self.gather_count_stat('Soldier\'s Aura', collector, True, False, soldiers_aura_events)