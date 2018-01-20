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
    ENEMY_TILE = 38184
    SAMAROG_CLAW = 37843
    SHOCKWAVE = 37996
    PRISONER_SWEEP = 38168
    CHARGE = 37797
    ANGUISHED_BOLT = 38314
    INEVITABLE_BETRAYL = 38260
    #Spear of Revulsion
    EFFIGY_PULSE = 37901
    BLUDGEON = 38305
    SAMAROG_FIXATE = 37868
    SMALL_FRIEND = 38247
    BIG_FRIEND = 37966
    ANNIHILATE = 38208
    SOUL_FEAST = 37805
    MIND_CRUSH = 37613
    RAPID_DECAY = 37716
    DEMONIC_SHOCKWAVE = 38046
    DEIMOS_PRIMARY_AGGRO = 34500
    DEIMOS_TELEPORT = 37838
    TEAR_CONSUMED = 37733
    RED_ORB = 34972
    WHITE_ORB = 34914
    RED_ORB_ATTUNEMENT = 35091
    WHITE_ORB_ATTUNEMENT = 35109
    COMPROMISED = 35096
    GAINING_POWER = 35075
    MAGIC_BLAST_INTENSITY = 35119
    SPEAR_IMPACT = 37816
    
    # Soulless Horror
    
    VORTEX_SLASH_INNER = 47327
    VORTEX_SLASH_OUTER = 48432
    DEATH_AOE = 47430
    PIE_SLICE = {48363, 47915}
    SCYTHE = 47363
    
    # Dhuum
    
    MESSENGER = 48172
    SHACKLE = 47335
    CRACK = 48752
    PUTRID_BOMB = 48760
    SUCK = 48398
    DEATH_MARK = 48176
    SNATCH = 47076
    TOXIC_SICKNESS = 37030

def standard_count(events):
    return len(events);
    
def combine_by_time_range_and_instid(events, time_range, inst_id = 'dst_instid'):
    events = events.sort_values(by=[inst_id, 'time'])
    deltas = abs(events.time - events.time.shift(1)) + (abs(events[inst_id] - events[inst_id].shift(1)) * 10000000)
    deltas.fillna(10000000, inplace=True)
    events = events.assign(deltas = deltas)
    events = events[events.deltas > time_range]
    return events

def generate_player_buff_times(events, players, skillid, encounter_end):
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

def gather_count_stat(name, collector, by_player, by_phase, phases, subgroups, players, events, calculation = standard_count):
    def count_by_phase(collector, events, func):
        split_by_phase(collector, func, events, phases)
    def count_by_player(collector, events):
        split_by_player_groups(collector, count, events, 'dst_instid', subgroups, players)
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

def gather_trio_stats(events, collector, agents, subgroups, players, bosses, phases, encounter_end):
    return

def gather_sh_stats(events, collector, agents, subgroups, players, bosses, phases, encounter_end):
    vortex_inner_events = events[(events.skillid == Skills.VORTEX_SLASH_INNER) & events.dst_instid.isin(players.index) & (events.value > 0)]
    vortex_outer_events = events[(events.skillid == Skills.VORTEX_SLASH_OUTER) & events.dst_instid.isin(players.index) & (events.value > 0)]
    death_aoe_events = events[(events.skillid == Skills.DEATH_AOE) & events.dst_instid.isin(players.index) & (events.value > 0)]
    pie_slice_events = events[(events.skillid.isin(Skills.PIE_SLICE)) & events.dst_instid.isin(players.index) & (events.value > 0)]
    sythe_events = events[(events.skillid == Skills.SCYTHE) & events.dst_instid.isin(players.index) & (events.value > 0)]
    
    gather_count_stat('Vortex (Inner)', collector, True, False, phases, subgroups, players, vortex_inner_events)
    gather_count_stat('Vortex (Outer)', collector, True, False, phases, subgroups, players, vortex_outer_events)
    gather_count_stat('Soul Rift', collector, True, False, phases, subgroups, players, death_aoe_events)
    gather_count_stat('Quad Slash', collector, True, False, phases, subgroups, players, pie_slice_events)
    gather_count_stat('Scythe Hits', collector, True, False, phases, subgroups, players, sythe_events)

def gather_dhuum_stats(events, collector, agents, subgroups, players, bosses, phases, encounter_end):
    messenger_events = events[(events.skillid == Skills.MESSENGER) & events.dst_instid.isin(players.index) & (events.value > 0)]
    shackle_events = events[(events.skillid == Skills.SHACKLE) & events.dst_instid.isin(players.index) & (events.value > 0)]
    crack_events = events[(events.skillid == Skills.CRACK) & events.dst_instid.isin(players.index) & (events.value > 0)]
    putrid_bomb_events = events[(events.skillid == Skills.PUTRID_BOMB) & events.dst_instid.isin(players.index) & (events.value > 0)]
    suck_events = events[(events.skillid == Skills.SUCK) & events.dst_instid.isin(players.index) & (events.value > 0)]
    death_mark_events = events[(events.skillid == Skills.DEATH_MARK) & events.dst_instid.isin(players.index) & (events.value > 0)]
    snatch_events = events[(events.skillid == Skills.SNATCH) & events.dst_instid.isin(players.index) & (events.value > 0)]
    toxic_sickness_events = events[(events.skillid == Skills.TOXIC_SICKNESS) & events.dst_instid.isin(players.index) & (events.value > 0)]
    
    gather_count_stat('Messenger', collector, True, False, phases, subgroups, players, messenger_events)
    gather_count_stat('Shackle Hits', collector, True, False, phases, subgroups, players, shackle_events)
    gather_count_stat('Fissured', collector, True, False, phases, subgroups, players, crack_events)
    gather_count_stat('Putrid Bomb', collector, True, False, phases, subgroups, players, putrid_bomb_events)
    gather_count_stat('Sucked', collector, True, False, phases, subgroups, players, suck_events)
    gather_count_stat('Death Marked', collector, True, False, phases, subgroups, players, death_mark_events)
    gather_count_stat('Snatched', collector, True, False, phases, subgroups, players, snatch_events)
    gather_count_stat('Toxic Sickness', collector, True, False, phases, subgroups, players, toxic_sickness_events)
        
def gather_vg_stats(events, collector, agents, subgroups, players, bosses, phases, encounter_end):
    teleport_events = events[(events.skillid == Skills.UNSTABLE_MAGIC_SPIKE) & events.dst_instid.isin(players.index) & (events.value > 0)]
    teleport_events = combine_by_time_range_and_instid(teleport_events, 1000)
    bullet_storm_events = events[(events.skillid == Skills.BULLET_STORM) & events.dst_instid.isin(players.index) & (events.value > 0)]
    gather_count_stat('Teleports', collector, True, False, phases, subgroups, players, teleport_events)
    gather_count_stat('Bullets Eaten', collector, True, False, phases, subgroups, players, bullet_storm_events)
    vg_blue_guardian_invul(events, collector)

def vg_blue_guardian_invul(events, collector):
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

    
def gather_gorse_stats(events, collector, agents, subgroups, players, bosses, phases, encounter_end):
    spectral_impact_events = events[(events.skillid == Skills.SPECTRAL_IMPACT) & events.dst_instid.isin(players.index) & (events.value > 0)]
    imprisonment_events = events[(events.skillid == Skills.GHASTLY_PRISON) & events.dst_instid.isin(players.index) & (events.is_buffremove == 0)]
    imprisonment_events = combine_by_time_range_and_instid(imprisonment_events, 1000)
    gather_count_stat('Unmitigated Spectral Impacts', collector, True, True, phases, subgroups, players, spectral_impact_events)
    gather_count_stat('Ghastly Imprisonments', collector, True, False, phases, subgroups, players, imprisonment_events)
    gorse_spectral_darkness_time('Spectral Darkness', collector, events, encounter_end, players, subgroups)

def gorse_spectral_darkness_time(name, collector, events, encounter_end, players, subgroups):
    times = generate_player_buff_times(events, players, Skills.SPECTRAL_DARKNESS, encounter_end)
    collector = collector.with_key(Group.PHASE, "All")
    def count(collector, times):
        collector.add_data(name, times['duration'].sum(), int)
    split_by_player_groups(collector, count, times, 'player', subgroups, players)

    
def gather_sab_stats(events, collector, agents, subgroups, players, bosses, phases, encounter_end):
    bomb_explosion_events = events[(events.skillid == Skills.HEAVY_BOMB_EXPLODE) & (events.is_buffremove == 1)]
    gather_count_stat('Heavy Bombs Undefused', collector, False, False, phases, subgroups, players, bomb_explosion_events)

    
def gather_sloth_stats(events, collector, agents, subgroups, players, bosses, phases, encounter_end):
    tantrum_hits = events[(events.skillid == Skills.TANTRUM) & events.dst_instid.isin(players.index) & (events.value > 0)]
    spores_received = events[(events.skillid == Skills.BLEEDING) & events.dst_instid.isin(players.index) & (events.value > 0) & (events.is_buffremove == 0)]
    spores_blocked = events[(events.skillid == Skills.BLEEDING) & events.dst_instid.isin(players.index) & (events.value == 0) & (events.is_buffremove == 0)]
    volatile_poison = events[(events.skillid == Skills.VOLATILE_POISON) & events.dst_instid.isin(players.index) & (events.buff == 1) & (events.is_buffremove == 0)]
    toxic_cloud = events[(events.skillid == Skills.TOXIC_CLOUD) & events.dst_instid.isin(players.index) & (events.value == 0)]                                                                                                                                          
    gather_count_stat('Tantrum Knockdowns', collector, True, False, phases, subgroups, players, tantrum_hits)
    gather_count_stat('Spores Received', collector, True, False, phases, subgroups, players, spores_received, lambda e: len(e) / 5)
    gather_count_stat('Spores Blocked', collector, True, False, phases, subgroups, players, spores_blocked, lambda e: len(e) / 5)
    gather_count_stat('Volatile Poison Carrier', collector, True, False, phases, subgroups, players, volatile_poison)
    gather_count_stat('Toxic Cloud Breathed', collector, True, False, phases, subgroups, players, toxic_cloud)                             

    
def gather_matt_stats(events, collector, agents, subgroups, players, bosses, phases, encounter_end):
    unbalanced_events = events[(events.skillid == Skills.UNBALANCED) & events.dst_instid.isin(players.index) & (events.buff == 0)]
    surrender_events = events[(events.skillid == Skills.SURRENDER) & events.dst_instid.isin(players.index) & (events.value > 0)]
    burning_events = events[(events.skillid == Skills.BURNING) & events.dst_instid.isin(players.index) & events.src_instid.isin(bosses.index) & (events.value > 0) & (events.buff == 1) & (events.is_buffremove == 0)]
    corrupted_events = events[(events.skillid == Skills.CORRUPTION) & events.dst_instid.isin(players.index) & (events.buff == 1) & (events.is_buffremove == 0)]
    blood_fueled_events = events[(events.skillid == Skills.BLOOD_FUELED) & (events.buff == 1) & (events.is_buffremove == 0)]
    sacrifice_events = events[(events.skillid == Skills.SACRIFICE) & (events.buff == 1) & (events.is_buffremove == 0)]
    profane_events = events[(events.skillid == Skills.UNSTABLE_BLOOD_MAGIC) & (events.buff == 1) & (events.is_buffremove == 0)]

    gather_count_stat('Moved While Unbalanced', collector, True, False, phases, subgroups, players, unbalanced_events)
    gather_count_stat('Surrender', collector, True, False, phases, subgroups, players, surrender_events)
    gather_count_stat('Burning Stacks Received', collector, True, True, phases, subgroups, players, burning_events)
    gather_count_stat('Corrupted', collector, True, False, phases, subgroups, players, corrupted_events)
    gather_count_stat('Matthias Shards Returned', collector, False, False, phases, subgroups, players,
                           blood_fueled_events[blood_fueled_events.dst_instid.isin(bosses.index)])
    gather_count_stat('Shards Absorbed', collector, True, False, phases, subgroups, players,
                           blood_fueled_events[blood_fueled_events.dst_instid.isin(players.index)])
    gather_count_stat('Sacrificed', collector, True, False, phases, subgroups, players, sacrifice_events)
    gather_count_stat('Well of the Profane Carrier', collector, True, False, phases, subgroups, players, profane_events)

    
def gather_kc_stats(events, collector, agents, subgroups, players, bosses, phases, encounter_end):
    orb_events = events[events.dst_instid.isin(players.index) & events.skillid.isin({Skills.RED_ORB_ATTUNEMENT, Skills.WHITE_ORB_ATTUNEMENT, Skills.RED_ORB, Skills.WHITE_ORB}) & (events.is_buffremove == 0)]

    orb_catch_events = generate_kc_orb_catch_events(players, orb_events)

    compromised_events = events[(events.skillid == Skills.COMPROMISED) & (events.is_buffremove == 0)]
    gaining_power_events = events[(events.skillid == Skills.GAINING_POWER) & (events.is_buffremove == 0)]
    magic_blast_intensity_events = events[(events.skillid == Skills.MAGIC_BLAST_INTENSITY) & (events.is_buffremove == 0)]

    gather_count_stat('Correct Orb', collector, True, False, phases, subgroups, players, orb_catch_events[orb_catch_events.correct == 1])
    gather_count_stat('Wrong Orb', collector, True, False, phases, subgroups, players, orb_catch_events[orb_catch_events.correct == 0])
    gather_count_stat('Rifts Hit', collector, False, False, phases, subgroups, players, compromised_events)
    gather_count_stat('Gaining Power', collector, False, False, phases, subgroups, players, gaining_power_events)
    gather_count_stat('Magic Blast Intensity', collector, False, False, phases, subgroups, players, magic_blast_intensity_events)

def generate_kc_orb_catch_events(players, events):               
    raw_data = np.array([np.arange(0, dtype=int)] * 3, dtype=int).T
    for player in list(players.index):
        data = np.array([np.arange(0)] * 2).T
        player_events = events[(events['dst_instid'] == player)]

        red_attuned = False
        for event in player_events.itertuples():
            if event.skillid == Skills.RED_ORB_ATTUNEMENT:
                red_attuned = True
            elif event.skillid == Skills.WHITE_ORB_ATTUNEMENT:
                red_attuned = False
            elif event.skillid == Skills.RED_ORB:
                data = np.append(data, [[event.time, red_attuned]], axis=0)
            elif event.skillid == Skills.WHITE_ORB:
                data = np.append(data, [[event.time, not red_attuned]], axis=0)

        data = np.c_[[player] * data.shape[0], data]
        raw_data = np.r_[raw_data, data]

    return pd.DataFrame(columns = ['dst_instid', 'time', 'correct'], data = raw_data)


def gather_xera_stats(events, collector, agents, subgroups, players, bosses, phases, encounter_end):
    derangement_events = events[(events.skillid == Skills.DERANGEMENT) & (events.buff == 1) & ((events.dst_instid.isin(players.index) & (events.is_buffremove == 0))|(events.src_instid.isin(players.index) & (events.is_buffremove == 1)))]
    gather_count_stat('Derangement', collector, True, False, phases, subgroups, players, derangement_events[derangement_events.is_buffremove == 0])
    #xera_derangement_max_stacks('Peak Derangement', collector, derangement_events, events.time.min(), players, subgroups)

def xera_derangement_max_stacks(name, collector, events, start_time, players, subgroups):
    events = events.sort_values(by='time')

    raw_data = np.array([np.arange(0, dtype=int)] * 2, dtype=int).T
    for player in list(players.index):
        player_events = events[((events['dst_instid'] == player)&(events.is_buffremove == 0))|
                               ((events['src_instid'] == player)&(events.is_buffremove == 1))]

        max_stacks = 0
        stacks = 0
        for event in player_events.itertuples():
            if event.is_buffremove == 0:
                stacks = stacks + 1
            elif event.is_buffremove == 1:
                print(str(event.time - start_time) + " - " + str(stacks))
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
    split_by_player_groups(collector, max_stacks, data, 'player', subgroups, players)

def gather_cairn_stats(events, collector, agents, subgroups, players, bosses, phases, encounter_end):
    displacement_events = events[(events.skillid == Skills.DISPLACEMENT) & events.dst_instid.isin(players.index) & (events.value > 0)]
    meteor_swarm_events = events[(events.skillid == Skills.METEOR_SWARM) & events.dst_instid.isin(players.index) & (events.value > 0)]
    meteor_swarm_events = combine_by_time_range_and_instid(meteor_swarm_events, 1000, 'dst_instid')

    spatial_manipulation_events = events[(events.skillid.isin(Skills.SPATIAL_MANIPULATION)) & events.dst_instid.isin(players.index) & (events.value > 0)]
    shared_agony_events = events[(events.skillid == Skills.SHARED_AGONY) & events.dst_instid.isin(players.index) & (events.buff == 1) & (events.is_buffremove == 0)] 
    gather_count_stat('Displacement', collector, True, False, phases, subgroups, players, displacement_events)
    gather_count_stat('Meteor Swarm', collector, True, False, phases, subgroups, players, meteor_swarm_events)
    gather_count_stat('Spatial Manipulation', collector, True, False, phases, subgroups, players, spatial_manipulation_events)
    gather_count_stat('Shared Agony', collector, True, False, phases, subgroups, players, shared_agony_events)


def gather_mursaat_overseer_stats(events, collector, agents, subgroups, players, bosses, phases, encounter_end):
    protect_events = events[(events.skillid == Skills.PROTECT) & events.dst_instid.isin(players.index) & (events.buff == 1) & (events.is_buffremove == 1)]
    claim_events = events[(events.skillid == Skills.CLAIM) & events.dst_instid.isin(players.index) & (events.buff == 1) & (events.is_buffremove == 1)]
    dispel_events = events[(events.skillid == Skills.DISPEL) & events.dst_instid.isin(players.index) & (events.buff == 1) & (events.is_buffremove == 1)]
    soldiers_aura_events = events[(events.skillid == Skills.SOLDIERS_AURA) & events.dst_instid.isin(players.index) & (events.value > 0)]
    soldiers = events[(events.skillid == Skills.SOLDIERS_AURA)].groupby('src_instid').first()
    enemy_tile_events = events[(events.skillid == Skills.ENEMY_TILE) & events.dst_instid.isin(players.index)]

    gather_count_stat('Protect', collector, True, False, phases, subgroups, players, protect_events)
    gather_count_stat('Claim', collector, True, False, phases, subgroups, players, claim_events)
    gather_count_stat('Dispel', collector, True, False, phases, subgroups, players, dispel_events)
    gather_count_stat('Soldiers', collector, False, False, phases, subgroups, players, soldiers)
    gather_count_stat('Soldier\'s Aura', collector, True, False, phases, subgroups, players, soldiers_aura_events)
    gather_count_stat('Enemy Tile', collector, True, False, phases, subgroups, players, enemy_tile_events)

def gather_samarog_stats(events, collector, agents, subgroups, players, bosses, phases, encounter_end):
    claw_events = events[(events.skillid == Skills.SAMAROG_CLAW) & events.dst_instid.isin(players.index) & (events.value > 0)]
    shockwave_events = events[(events.skillid == Skills.SHOCKWAVE) & events.dst_instid.isin(players.index) & (events.value > 0)]
    sweep_events = events[(events.skillid == Skills.PRISONER_SWEEP) & events.dst_instid.isin(players.index) & (events.value > 0)]
    charge_events = events[(events.skillid == Skills.CHARGE) & events.dst_instid.isin(players.index) & (events.value > 0)]
    guldhem_stun_events = events[(events.skillid == Skills.ANGUISHED_BOLT) & events.dst_instid.isin(players.index) & (events.value > 0)]
    inevitable_betrayl_events = events[(events.skillid == Skills.INEVITABLE_BETRAYL) & events.dst_instid.isin(players.index) & (events.value > 0)]
    bludgeon_events = events[(events.skillid == Skills.BLUDGEON) & events.dst_instid.isin(players.index) & (events.value > 0)]
    fixate_events = events[(events.skillid == Skills.SAMAROG_FIXATE) & events.dst_instid.isin(players.index) & (events.buff == 1) & (events.is_buffremove == 0)]
    small_friend_events = events[(events.skillid == Skills.SMALL_FRIEND) & events.dst_instid.isin(players.index) & events.dst_instid.isin(players.index) & (events.value > 0)]
    big_friend_events = events[(events.skillid == Skills.BIG_FRIEND) & events.dst_instid.isin(players.index) & (events.buff == 1) & (events.is_buffremove == 0)]
    spear_impact_events = events[(events.skillid == Skills.SPEAR_IMPACT) & events.dst_instid.isin(players.index) & (events.value > 0)]

    gather_count_stat('Claw', collector, True, True, phases, subgroups, players, claw_events)
    gather_count_stat('Shockwave', collector, True, True, phases, subgroups, players, shockwave_events)
    gather_count_stat('Prisoner Sweep', collector, True, True, phases, subgroups, players, sweep_events)
    gather_count_stat('Charge', collector, True, False, phases, subgroups, players, charge_events)
    gather_count_stat('Anguished Bolt', collector, True, False, phases, subgroups, players, guldhem_stun_events)
    gather_count_stat('Inevitable Betrayl', collector, True, False, phases, subgroups, players, inevitable_betrayl_events)
    gather_count_stat('Bludgeon', collector, True, False, phases, subgroups, players, bludgeon_events)
    gather_count_stat('Fixate', collector, True, True, phases, subgroups, players, fixate_events)
    gather_count_stat('Small Friend', collector, True, True, phases, subgroups, players, small_friend_events)
    gather_count_stat('Big Friend', collector, True, True, phases, subgroups, players, big_friend_events)
    gather_count_stat('Spear Impact', collector, True, True, phases, subgroups, players, spear_impact_events)

def gather_deimos_stats(events, collector, agents, subgroups, players, bosses, phases, encounter_end):
    annihilate_events = events[(events.skillid == Skills.ANNIHILATE) & events.dst_instid.isin(players.index) & (events.value > 0)]
    soul_feast_events = events[(events.skillid == Skills.SOUL_FEAST) & events.dst_instid.isin(players.index) & (events.value > 0)]
    mind_crush_events = events[(events.skillid == Skills.MIND_CRUSH) & events.dst_instid.isin(players.index) & (events.value > 0)]
    rapid_decay_events = events[(events.skillid == Skills.RAPID_DECAY) & events.dst_instid.isin(players.index) & (events.value > 0)]
    shockwave_events = events[(events.skillid == Skills.DEMONIC_SHOCKWAVE) & events.dst_instid.isin(players.index) & (events.value > 0)]
    teleport_events = events[(events.skillid == Skills.DEIMOS_TELEPORT) & events.dst_instid.isin(players.index) & (events.buff == 1) & (events.is_buffremove == 0)]
    tear_consumed_events = events[(events.skillid == Skills.TEAR_CONSUMED) & events.dst_instid.isin(players.index) & (events.buff == 1) & (events.is_buffremove == 0)]

    gather_count_stat('Annihilate', collector, True, False, phases, subgroups, players, annihilate_events)
    gather_count_stat('Soul Feast', collector, True, False, phases, subgroups, players, soul_feast_events)
    gather_count_stat('Mind Crush', collector, True, False, phases, subgroups, players, mind_crush_events)
    gather_count_stat('Rapid Decay', collector, True, False, phases, subgroups, players, rapid_decay_events)        
    gather_count_stat('Demonic Shockwave', collector, True, False, phases, subgroups, players, shockwave_events) 
    gather_count_stat('Teleports', collector, True, False, phases, subgroups, players, teleport_events)
    gather_count_stat('Tear Consumed', collector, True, False, phases, subgroups, players, tear_consumed_events)

