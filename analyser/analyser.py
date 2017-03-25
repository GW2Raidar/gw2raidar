from enum import IntEnum
from evtcparser import *
import pandas as pd
import numpy as np
from functools import reduce
from .collector import *

# DEBUG
from sys import exit
import timeit

class Group:
    CATEGORY = "Category"
    PLAYER = "Player"
    PHASE = "Phase"
    DESTINATION = "To"
    SKILL = "Skill"

class LogType(IntEnum):
    UNKNOWN = 0
    POWER = 1
    CONDI = 2
    APPLY = 3
    ACTIVATION = 4
    STATUSREMOVE = 5

class ContextType:
    DURATION = "Duration"
    TOTAL_DAMAGE_FROM_SOURCE_TO_DESTINATION = "Total Damage"
    TOTAL_DAMAGE_TO_DESTINATION = "Target Damage"
    SKILL_NAME = "Skill Name"
    AGENT_NAME = "Agent Name"
    PROFESSION_NAME = "Profession Name"


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
    def __init__(self, name, profs, invuln=None):
        self.name = name
        self.profs = profs
        self.invuln = invuln

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
BOSSES = {boss.profs[0]: boss for boss in BOSS_ARRAY}

def collect_individual_status(collector, player):
    only_entry = player.iloc[0]
    collector.add_data('profession', parser.AgentType(only_entry['prof']).name, str)
    collector.add_data('is_elite', only_entry['elite'], bool)
    collector.add_data('toughness', only_entry['toughness'], int)
    collector.add_data('healing', only_entry['healing'], int)
    collector.add_data('condition', only_entry['condition'], int)
    collector.add_data('archetype', only_entry['archetype'], str)
    collector.add_data('account', only_entry['account'], str)


def collect_player_status(collector, players):
    # player archetypes
    players = players.assign(archetype="Power")  # POWER
    players.loc[players.condition >= 7, 'archetype'] = "Condi"  # CONDI
    players.loc[players.toughness >= 7, 'archetype'] = "Tank"  # TANK
    players.loc[players.healing >= 7, 'archetype'] = "Heal"  # HEAL
    collector.group(collect_individual_status, players, ('name', 'Name'))

def collect_group_damage(collector, events):
    power_events = events[events.type == LogType.POWER]
    condi_events = events[events.type == LogType.CONDI]
    # print(events.columns)
    collector.add_data('power', power_events['damage'].sum(), int)
    collector.add_data('condi', condi_events['damage'].sum(), int)
    collector.add_data('total', events['damage'].sum(), int)

def collect_power_skill_data(collector, events):

    collector.add_data('fifty', events['is_fifty'].mean(), percentage)
    collector.add_data('scholar', events['is_ninety'].mean(), percentage)
    collector.add_data('seaweed', events['is_moving'].mean(), percentage)
    collector.add_data('total', events['damage'].sum(), int)
    collector.add_data('dps', events['damage'].sum(), per_second(int))
    collector.add_data('percentage', events['damage'].sum(),
                       percentage_of(ContextType.TOTAL_DAMAGE_FROM_SOURCE_TO_DESTINATION))

def collect_condi_skill_data(collector, events):
    collector.add_data('total', events['damage'].sum(), int)
    collector.add_data('dps', events['damage'].sum(), per_second(int))
    collector.add_data('percentage', events['damage'].sum(),
                       percentage_of(ContextType.TOTAL_DAMAGE_FROM_SOURCE_TO_DESTINATION))

def collect_individual_damage(collector, events):
    power_events = events[events.type == LogType.POWER]
    condi_events = events[events.type == LogType.CONDI]
    collector.set_context_value(ContextType.TOTAL_DAMAGE_FROM_SOURCE_TO_DESTINATION,
                                events['damage'].sum())
    # print(events.columns)
    collector.add_data('fifty', power_events['is_fifty'].mean(), percentage)
    collector.add_data('scholar', power_events['is_ninety'].mean(), percentage)
    collector.add_data('seaweed', power_events['is_moving'].mean(), percentage)
    collector.add_data('power', power_events['damage'].sum(), int)
    collector.add_data('condi', condi_events['damage'].sum(), int)
    collector.add_data('total', events['damage'].sum(), int)
    collector.add_data('power_dps', power_events['damage'].sum(), per_second(int))
    collector.add_data('condi_dps', condi_events['damage'].sum(), per_second(int))
    collector.add_data('dps', events['damage'].sum(), per_second(int))
    collector.add_data('percentage', events['damage'].sum(),
                       percentage_of(ContextType.TOTAL_DAMAGE_TO_DESTINATION))

    collector.group(collect_power_skill_data, power_events,
                    ('skillid', Group.SKILL, mapped_to(ContextType.SKILL_NAME)))
    collector.group(collect_condi_skill_data, condi_events,
                    ('skillid', Group.SKILL, mapped_to(ContextType.SKILL_NAME)))

def collect_destination_damage(collector, damage_events):
    collector.set_context_value(ContextType.TOTAL_DAMAGE_TO_DESTINATION,
                                damage_events['damage'].sum())
    collector.group(collect_group_damage, damage_events)
    collector.group(collect_individual_damage, damage_events, ('name', Group.PLAYER))

def collect_phase_damage(collector, damage_events):
    collector.set_context_value(ContextType.DURATION, float(damage_events['time'].max() - damage_events['time'].min())/1000.0)
    collector.group(collect_destination_damage, damage_events, ('destination_name', Group.DESTINATION))
    collector.with_key(Group.DESTINATION, "All").run(collect_destination_damage, damage_events)

def collect_damage(collector, player_events):
    player_events = assign_event_types(player_events)
    damage_events = player_events[(player_events.type == LogType.POWER)|(player_events.type == LogType.CONDI)]
    damage_events = damage_events.assign(damage = np.where(damage_events.type == LogType.POWER,
                                           damage_events['value'], damage_events['buff_dmg']))

    collector.with_key(Group.PHASE, "All").run(collect_phase_damage, damage_events)

    phases = []
    for i in range(0,len(phases)):
        phase_events = damage_events
        collector.with_key(Group.PHASE, "Phase {0}".format(i)).run(collect_phase_damage, phase_events)

class Analyser:
    def __init__(self, encounter):
        collector = Collector.root([Group.CATEGORY, Group.PHASE, Group.PLAYER, Group.DESTINATION, Group.SKILL])

        # ultimate source (e.g. if necro minion attacks, the necro himself)
        events = encounter.events
        agents = encounter.agents
        skills = encounter.skills

        skill_map = dict([(key, skills.loc[key, 'name']) for key in skills.index])
        collector.set_context_value(ContextType.SKILL_NAME, skill_map)
        destination_agents = agents.copy(True)
        destination_agents.columns = destination_agents.columns.str.replace('name', 'destination_name')

        events['ult_src_instid'] = events.src_master_instid.where(events.src_master_instid != 0, events.src_instid)
        players = agents[agents.party != 0]
        player_events = events.join(
            players[['name', 'account']], how='right', on='ult_src_instid').join(
            destination_agents[['destination_name']], how='right', on='dst_instid').sort_values(
            by='time')

        collector.with_key(Group.CATEGORY, "status").run(collect_player_status, players)
        collector.with_key(Group.CATEGORY, "damage").run(collect_damage, player_events)

        # awareness is defined as interval between first skill use
        # and last skill use, on (dst) or by (src) an agent
        # (e.g. casting a spell on VG makes it aware;
        # being hit by VG's teleport also makes it aware)
        aware_as_src = events.groupby('ult_src_instid')['time']
        aware_as_dst = events.groupby('dst_instid')[
            'time']  # XXX necessary to also include minions for destination awareness detection?
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

        # get player events (players are the only agents in a party)

        # TODO for speed we can convert join into restriction
        # (join gives more context for debugging)
        # For most of the metrics, we only care about the events
        # originating from players, that happen during the encounter;
        # then slice those player events based on DeltaConnected's
        # description into different sets.
        player_events = events.join(players[['name', 'account']], how='right', on='ult_src_instid').sort_values(
            by='time')
        player_events = player_events[player_events.time.between(encounter_start, encounter_end)]



        # most of the events below need to not be state change events, even
        # though DeltaConnected does not mention it
        not_state_change_events = player_events[player_events.state_change == parser.StateChange.NORMAL]

        # DeltaConnected:
        # > on cbtitem.is_activation == cancel_fire or cancel_cancel, value will be the ms duration of the approximate channel.
        cancel_fire_events = not_state_change_events[
            not_state_change_events.is_activation == parser.Activation.CANCEL_FIRE]
        cancel_cancel_events = not_state_change_events[
            not_state_change_events.is_activation == parser.Activation.CANCEL_CANCEL]
        not_cancel_events = not_state_change_events[
            not_state_change_events.is_activation < parser.Activation.CANCEL_FIRE]

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
            hit_gap_duration = hit_events.join(boss_agents['prof'], on='dst_instid', rsuffix='_dst', how='inner')[
                'time'].diff()
            gap_events = hit_events[['time']].assign(hit_gap_duration=hit_gap_duration)
            gap_events = gap_events[gap_events.hit_gap_duration > boss.invuln]
            gap_events['start'] = (gap_events.time - gap_events.hit_gap_duration).astype(np.uint64)
            time -= gap_events['hit_gap_duration'].sum()

        # get only events that happened while the boss was not invulnerable
        def non_gap(events):
            if gap_events is None or gap_events.empty:
                return events
            else:
                in_gap = reduce(lambda x, y: x | y,
                                [events.time.between(gap.start, gap.time) for gap in gap_events.itertuples()])
                return events[-in_gap]

        # damage sums
        direct_damage_to_boss_events = non_gap(
            hit_events.join(boss_agents['prof'], on='dst_instid', rsuffix='_dst', how='inner'))
        condi_damage_to_boss_events = non_gap(
            condi_events.join(boss_agents['prof'], on='dst_instid', rsuffix='_dst', how='inner'))

        direct_damage_to_boss_events_by_player = direct_damage_to_boss_events.groupby('ult_src_instid')
        condi_damage_to_boss_events_by_player = condi_damage_to_boss_events.groupby('ult_src_instid')

        condi_damage_by_player = non_gap(condi_events).groupby('ult_src_instid')['buff_dmg'].sum()
        direct_damage_by_player = non_gap(hit_events).groupby('ult_src_instid')['value'].sum()
        condi_damage_by_player_to_boss = condi_damage_to_boss_events_by_player['buff_dmg'].sum()
        direct_damage_by_player_to_boss = direct_damage_to_boss_events_by_player['value'].sum()

        # hit percentage while under special condition
        direct_damage_to_boss_count = direct_damage_to_boss_events_by_player['value'].count()

        flanking_hits_by_player_to_boss_count = \
        direct_damage_to_boss_events[direct_damage_to_boss_events.is_flanking != 0].groupby('ult_src_instid')[
            'value'].count()
        flanking = flanking_hits_by_player_to_boss_count / direct_damage_to_boss_count

        ninety_hits_by_player_to_boss_count = \
        direct_damage_to_boss_events[direct_damage_to_boss_events.is_ninety != 0].groupby('ult_src_instid')[
            'value'].count()
        ninety = ninety_hits_by_player_to_boss_count / direct_damage_to_boss_count

        moving_hits_by_player_to_boss_count = \
        direct_damage_to_boss_events[direct_damage_to_boss_events.is_moving != 0].groupby('ult_src_instid')[
            'value'].count()
        moving = moving_hits_by_player_to_boss_count / direct_damage_to_boss_count

        # identify the timestamp that represents the start of the log, and the
        # tick ('time') that is equivalent to it
        start_event = events[events.state_change == parser.StateChange.LOG_START]
        start_timestamp = start_event['value'][0]
        start_time = start_event['time'][0]

        # boons (status application events from players targetting players)
        # because boons linger, we can't use non_gap(apply_events)
        # TODO ignore gaps for totals later
        # because this is dipping into Python, we want only the necessary data
        boon_events = (apply_events[apply_events.dst_instid.isin(players.index)]
                       [['skillid', 'time', 'value', 'overstack_value', 'is_buffremove', 'dst_instid']])
        player_or_none = list(players.index) + [0]
        boonremove_events = (statusremove_events[statusremove_events.dst_instid.isin(player_or_none)]
                             [['skillid', 'time', 'value', 'overstack_value', 'is_buffremove', 'dst_instid']])
        boon_update_events = pd.concat([boon_events, boonremove_events]).sort_values('time')
        for event in boon_update_events.itertuples():
            pass  # TODO

        # saved as a JSON dump
        self.data = collector.all_data
