__author__ = 'Owner'
from analyser.analyser import Archetype
from analyser.buffs import BUFF_TYPES

FULL_SUPPORT_CUTOFF = 8
PARTICIPANT_INACTIVITY_CUTOFF = 0.8
def postprocess(encounter, participation, data):
    simple_archetype = participation.simple_archetype
    if(simple_archetype < 0):
        simple_archetype = participation.archetype

    all_phase_stats = data['Category']['combat']['Phase']['All']
    all_to_boss = all_phase_stats['Subgroup']['*All']

    print("Revising archetype for character", participation.character)
    all_players = all_phase_stats['Player']
    player_stats = all_players[participation.character]
    squad_dps = all_to_boss['Metrics']['damage']['To']['*Boss']['dps']

    event_stats = player_stats['Metrics']['events']
    down_time = event_stats.get('down_time', 0)
    disconnect_time= event_stats.get('disconnect_time', 0)
    dead_time = event_stats.get('dead_time', 0)
    inactivity_duration = ((down_time / 1000) + (dead_time / 1000) + (disconnect_time / 1000))

    buff_info_strings = []
    inactivity_factor = float(inactivity_duration) / encounter.duration
    if inactivity_factor >=  PARTICIPANT_INACTIVITY_CUTOFF:
        new_archetype = Archetype.NON_PARTICIPANT
        participation.archetype_debug_info = "Mostly dead"
        description = "Non-participant: inactive more than {0}% of the fight".format(
            int(PARTICIPANT_INACTIVITY_CUTOFF * 100))
    else:
        damage_stats = player_stats['Metrics']['damage']['To']['*Boss']
        #print(damage_stats)
        condi = damage_stats['condi_dps']
        power = damage_stats['power_dps']
        total = damage_stats['dps']

        multiplier = 2/len(all_players)
        support_level = 0

        condi = condi > power
        description = "Did more {0} damage than {1} damage{2}<br>".format(
            "Condi" if condi else "Power", "Power" if condi else "Condi", "{0}")
        if (simple_archetype not in [Archetype.POWER, Archetype.CONDI]
                and total < squad_dps * multiplier):
            support_level = 2
            description = "High healing power or toughness and low damage.<br>"


        outgoing_buff_stats = _safe_get(lambda: player_stats['Metrics']['buffs']['To']['*All'], {})

        support_power = 0
        for buff in BUFF_TYPES:
            if buff.code in outgoing_buff_stats:
                metric = outgoing_buff_stats[buff.code]
                if(metric > buff.arch_uptime):
                    buff_info_strings.append("{0} - {1}%".format(
                        buff.name, (100 * buff.arch_support_power)/FULL_SUPPORT_CUTOFF))
                    support_power += buff.arch_support_power

        if support_power >= FULL_SUPPORT_CUTOFF:
            description = "Provided a huge amount of buffs.<br>"
            support_level = 2
        elif support_power >= FULL_SUPPORT_CUTOFF/2 and support_level < 1:
            support_level = 1
            description = description.format(" and provided some buffs to the team")
        else:
            description = description.format("")

        description += "Substantial buff output - {0}% of a support player:<br>{1}".format(
            (100 * support_power)/FULL_SUPPORT_CUTOFF,
            "<br>".join(buff_info_strings) if buff_info_strings else "No substantial buff output")

        if support_level >= 2:
            new_archetype = Archetype.SUPPORT
        elif support_level >= 1:
            if condi:
                new_archetype = Archetype.HYBRID_CONDI
            else:
                new_archetype = Archetype.HYBRID_POWER
        else:
            if condi:
                new_archetype = Archetype.CONDI
            else:
                new_archetype = Archetype.POWER


    participation.archetype_debug_info = description
    participation.simple_archetype = simple_archetype
    participation.archetype = new_archetype

def _safe_get(func, default=0):
    try:
        return func()
    except (KeyError, TypeError):
        return default