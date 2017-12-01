__author__ = 'Owner'
from analyser.analyser import Archetype

def something(participation, data):
    all_phase_stats = data['Category']['combat']['Phase']['All']
    all_to_boss = all_phase_stats['Subgroup']['*All']

    player_stats = all_phase_stats['Player'][participation.character.name]
    condi = player_stats['Metrics']['condi']['To']['*Boss']
    power = player_stats['Metrics']['power']['To']['*Boss']
    total = player_stats['Metrics']['damage']['To']['*Boss']

    multiplier = 2/data.playerCount
    if (participation.archetype not in [Archetype.POWER, Archetype.CONDI]
            and total < all_to_boss * multiplier):
        participation.new_archetype = Archetype.SUPPORT
    elif power > condi:
        participation.new_archetype = Archetype.POWER
    else:
        participation.new_archetype = Archetype.CONDI

    participation.buff_stuff = data
