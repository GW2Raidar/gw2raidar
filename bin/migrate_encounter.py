from datetime import datetime
import json
import sys

data_out = []
app = "raidar"
encounter_id = 0


def generate_buff_data(prv_phase_name, prv_buff_source, prv_buff_target, prv_buff_name, prv_buff_data):
    return {
        "model": app + ".EncounterBuff",
        "fields": {
            "encounter_id": encounter_id,
            "phase": prv_phase_name,
            "source": prv_buff_source,
            "target": prv_buff_target,
            "buff": prv_buff_name,
            "uptime": prv_buff_data if prv_buff_name == "might" else (prv_buff_data / 100.0),
        }}


def generate_skill_data(prv_phase_name, prv_skill_source, prv_skill_target, prv_skill_name, prv_skill_data):
    return {
        "model": app + ".EncounterDamage",
        "fields": {
            "encounter_id": encounter_id,
            "phase": prv_phase_name,
            "source": prv_skill_source,
            "target": prv_skill_target,
            "skill": prv_skill_name,
            "damage": prv_skill_data["total"],
            "crit": (prv_skill_data["crit"] / 100.0) if "crit" in prv_skill_data else 0,
            "fifty": (prv_skill_data["fifty"] / 100.0) if "fifty" in prv_skill_data else 0,
            "flanking": (prv_skill_data["flanking"] / 100.0) if "flanking" in prv_skill_data else 0,
            "scholar": (prv_skill_data["scholar"] / 100.0) if "scholar" in prv_skill_data else 0,
            "seaweed": (prv_skill_data["seaweed"] / 100.0) if "seaweed" in prv_skill_data else 0,
        }}


for arg in sys.argv:
    buff_count = 0
    skill_count = 0

    if arg == sys.argv[0]:
        continue
    with open(sys.argv[1]) as json_file:
        encounter_id += 1
        data = json.load(json_file)["Category"]

        encounter = {"model": app + ".EncounterData", "pk": encounter_id, "fields": {
            "boss": "",
            "cm": data["encounter"]["cm"],
            "start_timestamp": str(datetime.fromtimestamp(data["encounter"]["start"])),
            "start_tick": data["encounter"]["start_tick"],
            "end_tick": data["encounter"]["end_tick"],
            "success": data["encounter"]["success"],
            "evtc_version": data["encounter"]["evtc_version"],
        }}
        for boss_name in data["boss"]["Boss"]:
            encounter["fields"]["boss"] += boss_name
        data_out.append(encounter)

        for phase_name, phase_data in data["encounter"]["Phase"].items():
            phase = {"model": app + ".EncounterPhase", "fields": {
                "encounter_id": encounter_id,
                "phase": phase_name,
                "start_tick": phase_data["start_tick"],
            }}
            data_out.append(phase)

        for player_name, player_data in data["status"]["Player"].items():
            player = {"model": app + ".EncounterPlayer", "fields": {
                "encounter_id": encounter_id,
                "account_id": player_data["account"],
                "character": player_name,
                "party": player_data["party"],
                "profession": player_data["profession"],
                "elite": player_data["elite"],
                "archetype": player_data["archetype"],
                "conc": player_data["concentration"],
                "condi": player_data["condition"],
                "heal": player_data["healing"],
                "tough": player_data["toughness"],
            }}
            data_out.append(player)

        for phase_name, phase_data in data["combat"]["Phase"].items():
            if phase_name == "All":
                continue
            for player_name, player_data in phase_data["Player"].items():
                player_data = player_data["Metrics"]

                # Buffs
                # Incoming
                for buff_source in player_data["buffs"]["From"]:
                    buff_target = player_name
                    for buff_name, buff_data in player_data["buffs"]["From"][buff_source].items():
                        if buff_data > 0:
                            buff = generate_buff_data(phase_name, buff_source, buff_target, buff_name, buff_data)
                            data_out.append(buff)
                            buff_count += 1
                # Outgoing
                for buff_target in player_data["buffs"]["To"]:
                    buff_source = player_name
                    for buff_name, buff_data in player_data["buffs"]["To"][buff_target].items():
                        if buff_data > 0:
                            buff = generate_buff_data(phase_name, buff_source, buff_target, buff_name, buff_data)
                            data_out.append(buff)
                            buff_count += 1

                # Damage
                # Incoming
                for skill_source in player_data["damage"]["From"]:
                    skill_target = player_name
                    for skill_name, skill_data in player_data["damage"]["From"][skill_source]["Skill"].items():
                        skill = generate_skill_data(phase_name, skill_source, skill_target, skill_name, skill_data)
                        data_out.append(skill)
                        skill_count += 1
                # Outgoing
                for skill_target, skill_target_data in player_data["damage"]["To"].items():
                    skill_source = player_name
                    # Skill breakdown
                    if skill_target == "*All" and "Skill" in skill_target_data:
                        for skill_name, skill_data in skill_target_data["Skill"].items():
                            skill = generate_skill_data(phase_name, skill_source, skill_target, skill_name, skill_data)
                            data_out.append(skill)
                            skill_count += 1
                    # Summary
                    else:
                        # Condi
                        if skill_target_data["condi"] > 0:
                            condi = generate_skill_data(phase_name, skill_source, skill_target, "condi", skill_target_data)
                            condi["fields"]["damage"] = skill_target_data["condi"]
                            data_out.append(condi)
                            skill_count += 1
                        # Power
                        if skill_target_data["power"] > 0:
                            power = generate_skill_data(phase_name, skill_source, skill_target, "power", skill_target_data)
                            power["fields"]["damage"] = skill_target_data["power"]
                            data_out.append(power)
                            skill_count += 1

                # Events
                event_data = player_data["events"]
                event = {"model": app + ".EncounterEvent", "fields": {
                    "encounter_id": encounter_id,
                    "phase": phase_name,
                    "source": player_name,
                    "disconnect_count": event_data["disconnects"],
                    "disconnect_time": int(event_data["disconnect_time"]),
                    "down_count": event_data["downs"],
                    "down_time": int(event_data["down_time"]),
                }}
                data_out.append(event)

                # Shielded
                shield_data = player_data["shielded"]["From"]["*All"]
                shield_source = "*All"
                shield_target = player_name
                shield = generate_skill_data(phase_name, skill_source, skill_target, "shielded", skill_data)
                shield["fields"]["damage"] = -shield["fields"]["damage"]
                data_out.append(shield)
                skill_count += 1

                # Mechanics
                if "mechanics" in player_data:
                    for mechanic_name, mechanic_data in player_data["mechanics"].items():
                        mechanic = {"model": app + ".EncounterMechanic", "fields": {
                            "encounter_id": encounter_id,
                            "phase": phase_name,
                            "source": player_name,
                            "mechanic": mechanic_name,
                            "count": mechanic_data
                        }}
                        data_out.append(mechanic)


print(json.dumps(data_out, indent=2))
# print(str(buff_count) + " buffs, " + str(skill_count) + " skills, " + str(buff_count + skill_count) + " total.")
