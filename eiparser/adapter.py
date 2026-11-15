"""Converts an Elite Insights JSON log into the dict consumed by
``raidar.models.EncounterData.from_dump``.

This module is deliberately free of Django imports so it can be exercised
directly against EI output files.

All per-actor statistics in the EI JSON are lists indexed by phase; phase 0
is always the full fight. EI times are milliseconds relative to log start.
"""
from datetime import datetime

from analyser.analyser import Archetype, SPECIALISATION_BY_NAME
from analyser.buffs import BUFF_CATEGORIES, BUFF_CODES_BY_ID, BUFF_TYPES, buff_code

BOON_CODES = frozenset(buff.code for buff in BUFF_TYPES)

ALL_PHASE = "All"
ALL = "*All"
BOSS = "*Boss"

MAX_PLAYERS = 50

# Mechanics EI adds to every log that only repeat data the site already shows
# (deaths/downs) or that are guesses about boon coverage rather than fight mechanics.
IGNORED_MECHANICS = frozenset(["Dead", "Downed", "Got up", "Res", "Miss.Qck", "Miss.Alac"])


class EIAdapterException(Exception):
    """The log was parsed by EI but cannot be used by the site; the message is shown to the uploader."""


def _percent(part, whole):
    return 100.0 * part / whole if whole else 0.0


def _per_second(amount, duration_ms):
    return amount * 1000.0 / duration_ms if duration_ms > 0 else 0.0


def _unique(name, taken):
    candidate, index = name, 1
    while candidate in taken:
        index += 1
        candidate = "%s (%d)" % (name, index)
    taken.add(candidate)
    return candidate


def _archetype(player):
    # same rule the previous analyser used; ArcDPS reports these stats as 0-10
    if player["toughness"] >= 5 or player["healing"] >= 5 or player["concentration"] >= 3:
        return Archetype.SUPPORT
    if player["condition"] >= 5:
        return Archetype.CONDI
    return Archetype.POWER


def _select_players(log):
    players = [player for player in log.get("players") or []
               if not player.get("isFake") and not player.get("friendlyNPC") and player.get("account")]
    if not players:
        raise EIAdapterException("No players found in this log")
    if len(players) > MAX_PLAYERS:
        raise EIAdapterException("Too many players found in this log: {0}".format(len(players)))
    for player in players:
        if player["profession"] not in SPECIALISATION_BY_NAME:
            raise EIAdapterException("Unknown specialisation: {0}".format(player["profession"]))
    return players


def _select_phases(log):
    """Returns [(index into EI's phase list, unique name, phase)], the full fight first, named "All".

    Breakbar phases are dropped: they overlap the fight phases and only describe one target's defiance bar.
    """
    phases = log.get("phases") or []
    if not phases:
        raise EIAdapterException("No phases found in this log")
    taken = {ALL_PHASE}
    selected = [(0, ALL_PHASE, phases[0])]
    for index, phase in enumerate(phases[1:], 1):
        if phase.get("breakbarPhase") or phase["end"] <= phase["start"]:
            continue
        selected.append((index, _unique(phase.get("name") or "Phase %d" % index, taken), phase))
    return selected


def _phase_parents(log, phases):
    """Returns {phase name: name of the phase it is a part of, or None for the top level phases}.

    EI lists the direct sub phases of every phase (JsonPhase.subPhases); the full fight is the root and is not
    a parent: its sub phases are the top level phases.
    """
    ei_phases = log.get("phases") or []
    name_by_index = {index: name for index, name, _ in phases}
    parents = {}
    for index, name, phase in phases[1:]:
        candidates = [other for other, other_name, other_phase in phases[1:]
                      if index in (other_phase.get("subPhases") or []) and other != index]
        # should several phases claim this one, the shortest is the closest
        parent = min(candidates, key=lambda other: ei_phases[other]["end"] - ei_phases[other]["start"],
                     default=None)
        parents[name] = name_by_index[parent] if parent is not None else None
    return parents


class _SkillNames:
    def __init__(self, log):
        self.skills = log.get("skillMap") or {}
        self.buffs = log.get("buffMap") or {}

    def name(self, entry):
        skill_id = entry["id"]
        first, second = (self.buffs.get("b%d" % skill_id), self.skills.get("s%d" % skill_id))
        if not entry.get("indirectDamage"):
            first, second = second, first
        for desc in (first, second):
            if desc and desc.get("name"):
                return desc["name"]
        return str(skill_id)


def _skill_breakdown(dists, names):
    """Aggregates EI damage distribution entries by skill name (several skill IDs can share a name)."""
    skills = {}
    for entry in dists:
        skill = skills.setdefault(names.name(entry), {"total": 0, "hits": 0, "crit": 0, "flank": 0, "moving": 0})
        skill["total"] += entry["totalDamage"]
        skill["hits"] += entry["connectedHits"]
        skill["crit"] += entry["crit"]
        skill["flank"] += entry["flank"]
        skill["moving"] += entry["againstMoving"]
    return {
        name: {
            "total": skill["total"],
            "crit": _percent(skill["crit"], skill["hits"]),
            "flanking": _percent(skill["flank"], skill["hits"]),
            "seaweed": _percent(skill["moving"], skill["hits"]),
            # EI does not break these two down by skill
            "scholar": 0.0,
            "fifty": 0.0,
        } for name, skill in skills.items() if skill["total"] > 0
    }


_DPS_FIELDS = ("damage", "powerDamage", "condiDamage", "breakbarDamage")
_STAT_FIELDS = ("criticalRate", "critableDirectDamageCount", "flankingRate", "connectedDirectDamageCount",
                "againstMovingRate", "connectedDamageCount", "connectedPowerAbove90HPCount", "connectedPowerCount")


def _outgoing_summary(dps_entries, stat_entries, duration_ms):
    """Builds the outgoing damage summary from EI JsonDPS / JsonGameplayStats entries (summed over targets)."""
    dps = {field: sum(entry.get(field) or 0 for entry in dps_entries) for field in _DPS_FIELDS}
    stats = {field: sum(entry[field] for entry in stat_entries) for field in _STAT_FIELDS}
    return {
        "total": dps["damage"],
        "power": dps["powerDamage"],
        "condi": dps["condiDamage"],
        # damage dealt to defiance bars
        "breakbar": dps["breakbarDamage"],
        "dps": _per_second(dps["damage"], duration_ms),
        "power_dps": _per_second(dps["powerDamage"], duration_ms),
        "condi_dps": _per_second(dps["condiDamage"], duration_ms),
        "crit": _percent(stats["criticalRate"], stats["critableDirectDamageCount"]),
        "flanking": _percent(stats["flankingRate"], stats["connectedDirectDamageCount"]),
        "seaweed": _percent(stats["againstMovingRate"], stats["connectedDamageCount"]),
        "scholar": _percent(stats["connectedPowerAbove90HPCount"], stats["connectedPowerCount"]),
        # share of hits against targets below 50% health: not computed by EI
        "fifty": 0.0,
    }


def _damage(player, index, phase, duration_ms, names):
    outgoing = _outgoing_summary([player["dpsAll"][index]], [player["statsAll"][index]], duration_ms)
    dists = list(player["totalDamageDist"][index])
    for minion in player.get("minions") or []:
        dists.extend(minion["totalDamageDist"][index])
    outgoing["Skill"] = _skill_breakdown(dists, names)

    targets = phase.get("targets") or []
    boss = _outgoing_summary([player["dpsTargets"][target][index] for target in targets],
                             [player["statsTargets"][target][index] for target in targets], duration_ms)

    defenses = player["defenses"][index]
    incoming = {
        "total": defenses["damageTaken"],
        "power": defenses["powerDamageTaken"],
        "condi": defenses["conditionDamageTaken"],
        "dps": _per_second(defenses["damageTaken"], duration_ms),
        "Skill": _skill_breakdown(player["totalDamageTaken"][index], names),
    }
    return {"To": {ALL: outgoing, BOSS: boss}, "From": {ALL: incoming}}


def _events(player, index):
    defenses = player["defenses"][index]
    return {
        "deaths": defenses["deadCount"],
        "downs": defenses["downCount"],
        "disconnects": defenses["dcCount"],
        "dead_time": defenses["deadDuration"],
        "down_time": defenses["downDuration"],
        "disconnect_time": defenses["dcDuration"],
    }


def _buff_info(log, players):
    """Returns ({EI buff ID: buff code}, [buff descriptions]) for the buffs the site shows.

    These are the buffs at least one player had during the fight that EI classifies as a boon or as an
    offensive, support or defensive buff. A description is {"code", "name", "category", "stacking", "icon"},
    where the category is the ID of the tab the buff is listed on.
    """
    tab_by_classification = {classification: tab for classification, tab, _ in BUFF_CATEGORIES}
    buff_map = log.get("buffMap") or {}
    code_by_id = {}
    info = {}
    for player in players:
        for buff in player.get("buffUptimes") or []:
            desc = buff_map.get("b%d" % buff["id"]) or {}
            tab = tab_by_classification.get(desc.get("classification"))
            if tab is None or not desc.get("name") or buff["id"] in code_by_id:
                continue
            code = buff_code(buff["id"], desc["name"])
            # a buff that only shares its name with a boon must not be merged into the boon
            if not code or (code in BOON_CODES and buff["id"] not in BUFF_CODES_BY_ID):
                continue
            code_by_id[buff["id"]] = code
            info.setdefault(code, {
                "code": code,
                "name": desc["name"],
                "category": tab,
                "stacking": bool(desc.get("stacking")),
                "icon": desc.get("icon") or "",
            })
    return code_by_id, sorted(info.values(), key=lambda buff: buff["name"])


def _buff_tables(players, index, code_by_id):
    """Returns ({player: {buff code: uptime}}, {player: {buff code: generation}}).

    Uptime is a percentage, or the average stack count for buffs stacking in intensity. Generation is what the
    player provided averaged over every squad member (themselves included), which is how the site has always
    measured outgoing buffs.
    """
    incoming = {player["name"]: {} for player in players}
    outgoing = {player["name"]: {} for player in players}
    for player in players:
        for buff in player.get("buffUptimes") or []:
            code = code_by_id.get(buff["id"])
            if code is None:
                continue
            data = buff["buffData"][index]
            uptime = incoming[player["name"]]
            uptime[code] = max(uptime.get(code, 0.0), data["uptime"])
            for source, generated in (data.get("generated") or {}).items():
                if source in outgoing:
                    outgoing[source][code] = outgoing[source].get(code, 0.0) + generated / len(players)
    return incoming, outgoing


def _mechanics(log, player_names, phases):
    """Returns (mechanic descriptions, {phase name: {player: {mechanic name: count}}})."""
    info = []
    counts = {name: {player: {} for player in player_names} for _, name, _ in phases}
    taken = set()
    for mechanic in log.get("mechanics") or []:
        hits = [hit for hit in mechanic.get("mechanicsData") or [] if hit.get("actor") in player_names]
        if not hits or mechanic.get("name") in IGNORED_MECHANICS:
            continue
        name = _unique(mechanic["name"], taken)
        full_name = mechanic.get("fullName") or name
        description = mechanic.get("description")
        info.append({
            "name": name,
            "short_name": name,
            "long_name": "%s: %s" % (full_name, description) if description and description != full_name
                         else full_name,
        })
        for _, phase_name, phase in phases:
            for hit in hits:
                if phase["start"] <= hit["time"] <= phase["end"]:
                    player_counts = counts[phase_name][hit["actor"]]
                    player_counts[name] = player_counts.get(name, 0) + 1
    return info, counts


def _start_timestamp(log):
    try:
        return int(datetime.strptime(log["timeStartStd"], "%Y-%m-%d %H:%M:%S %z").timestamp())
    except (KeyError, ValueError):
        raise EIAdapterException("This log has no usable start time")


def convert(log):
    """Converts a parsed EI JSON document. Raises EIAdapterException for logs the site cannot use."""
    if log.get("isInstanceLog"):
        raise EIAdapterException("Full instance logs are not supported, upload single encounter logs")
    if log.get("anonymous"):
        raise EIAdapterException("Anonymised logs are not supported")

    players = _select_players(log)
    player_names = [player["name"] for player in players]
    if len(set(player_names)) != len(player_names):
        raise EIAdapterException("Duplicate character names in this log")
    phases = _select_phases(log)
    phase_parents = _phase_parents(log, phases)
    names = _SkillNames(log)
    mechanics_info, mechanic_counts = _mechanics(log, set(player_names), phases)
    buff_codes, buff_info = _buff_info(log, players)

    full_fight = phases[0][2]
    combat = {}
    for index, phase_name, phase in phases:
        duration_ms = phase["end"] - phase["start"]
        buffs_in, buffs_out = _buff_tables(players, index, buff_codes)
        phase_players = {}
        for player in players:
            name = player["name"]
            phase_players[name] = {"Metrics": {
                "damage": _damage(player, index, phase, duration_ms, names),
                "shielded": {"From": {ALL: {"total": player["defenses"][index]["damageBarrier"]}}},
                "buffs": {"From": {ALL: buffs_in[name]}, "To": {ALL: buffs_out[name]}},
                "events": _events(player, index),
                "mechanics": mechanic_counts[phase_name][name],
            }}
        combat[phase_name] = {"Player": phase_players}

    status = {}
    for player in players:
        profession, elite = SPECIALISATION_BY_NAME[player["profession"]]
        status[player["name"]] = {
            "account": player["account"],
            "profession": int(profession),
            "elite": int(elite),
            "archetype": int(_archetype(player)),
            "party": player.get("group") or 0,
            "toughness": player["toughness"],
            "healing": player["healing"],
            "condition": player["condition"],
            "concentration": player["concentration"],
        }

    arc_version = log.get("arcVersion") or ""
    return {"Category": {
        "encounter": {
            "name": log.get("fightName") or log.get("name") or "",
            "ei_encounter_id": log.get("eiEncounterID") or 0,
            "trigger_id": log.get("triggerID") or 0,
            "parser_version": "EI %s" % (log.get("eliteInsightsVersion") or "unknown"),
            "evtc_version": arc_version[4:] if arc_version.startswith("EVTC") else arc_version,
            "start": _start_timestamp(log),
            "start_tick": full_fight["start"],
            "end_tick": full_fight["end"],
            "duration": (full_fight["end"] - full_fight["start"]) / 1000.0,
            "success": bool(log.get("success")),
            "cm": bool(log.get("isCM")),
            "legendary_cm": bool(log.get("isLegendaryCM")),
            "phase_order": [name for _, name, _ in phases],
            "Phase": {name: {
                "start_tick": phase["start"],
                "end_tick": phase["end"],
                "duration": (phase["end"] - phase["start"]) / 1000.0,
                "parent": phase_parents.get(name),
            } for _, name, phase in phases},
            "mechanics": mechanics_info,
            "buffs": buff_info,
        },
        "boss": {"Boss": {log.get("fightName") or log.get("name") or "Unknown": {}}},
        "status": {"Player": status},
        "combat": {"Phase": combat},
    }}
