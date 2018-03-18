__author__ = 'Owner'
from analyser.analyser import Archetype
from analyser.buffs import BUFF_TYPES

def something(participation, data):
    all_phase_stats = data['Category']['combat']['Phase']['All']
    all_to_boss = all_phase_stats['Subgroup']['*All']

    print("Revising archetype for character ", participation.character)
    player_stats = all_phase_stats['Player'][participation.character]

    damage_stats = player_stats['Metrics']['damage']['To']['*Boss']
    print(damage_stats)
    condi = damage_stats['condi_dps']
    power = damage_stats['power_dps']
    total = damage_stats['dps']

    multiplier = 2/data.playerCount
    if (participation.archetype not in [Archetype.POWER, Archetype.CONDI]
            and total < all_to_boss * multiplier):
        participation.support_level = 3
    participation.condi = condi > power

    outgoing_buff_stats = _safe_get(lambda: player_stats['Metrics']['buffs']['To']['*All'], {})
    buff_list = []
    for buff in BUFF_TYPES:
        metric = outgoing_buff_stats[buff.name]
        if(metric > buff.arch_uptime):
            buff_list.add(buff.name)


    if participation.support_level >= 3:
        participation.new_archetype_string = "Full support"
    else:
        if participation.condi:
            participation.new_archetype_string = "Condi"
        else:
            participation.new_archetype_string = "Power"

        if participation.support_level >= 2:
            participation.new_archetype_string += " Support"