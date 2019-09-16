"""
Raidar ReStat
=============

Offers a Django command to recalculate the distribution of encounter-related performance stats by analyzing all
new encounter logs and generating or updating any related percentile blobs.
"""
import copy
from contextlib import contextmanager
from datetime import timezone
from math import floor
from time import time
import os
import sys
import base64
import numpy
import psutil
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db.utils import IntegrityError
from raidar.models import Variable, Encounter, RestatPerfStats, EraAreaStore, EraUserStore, Era, settings, datetime, \
    Area, EncounterDamage, EncounterBuff, EncounterPlayer, EncounterEvent

# DEBUG: uncomment to log SQL queries
# import logging
# l = logging.getLogger("django.db.backends")
# l.setLevel(logging.DEBUG)
# l.addHandler(logging.StreamHandler())

AVG_STATS = ["crit", "flanking", "scholar", "seaweed"]
SUM_STATS = ["dps", "dps_boss", "dps_received", "total_shielded", "total_received"]
ALL_STATS = AVG_STATS + SUM_STATS

DEFAULT_AREA_STORE = {"All": {"group": {"count": 0, "buffs": {}, "buffs_out": {}},
                              "individual": {"count": 0},
                              "build": {"All": {"All": {"All": {"count": 0, "buffs": {}, "buffs_out": {}}}}}}}


@contextmanager
def single_process(name):
    """Locks this module to prevent parallel runs, or exits if already locked."""
    try:
        pid = os.getpid()
        # Remove "restat_pid" from raidar_variables table to lift lock manually
        pid_var = Variable.objects.create(key="%s_pid" % name, val=pid)
        try:
            yield pid
        finally:
            pid_var.delete()
    except IntegrityError:
        # Already running
        sys.exit()


def last_restat():
    """Determines the timespan since the last restat run by using RestatPerfStats."""
    last_run = RestatPerfStats.objects.order_by("-started_on").first()
    if last_run:
        return last_run.started_on
    return datetime.fromtimestamp(0, timezone.utc)


def delete_old_files():
    """Checks the upload file system for free space and deletes old log files if necessary."""
    gigabyte = 1024 * 1024 * 1024
    min_disk_avail = 10 * gigabyte
    num_pruned = 0

    encounters = Encounter.objects.filter(has_evtc=True).order_by("started_at")
    for encounter in encounters:
        # https://stackoverflow.com/questions/51658/cross-platform-space-remaining-on-volume-using-python
        if psutil.disk_usage(settings.UPLOAD_DIR).free < min_disk_avail:  # pylint: disable=no-member
            break

        filename = encounter.diskname()
        if filename:
            try:
                os.unlink(filename)
                num_pruned += 1
            except FileNotFoundError:
                pass
        encounter.has_evtc = False
        encounter.save()

    return num_pruned


class Command(BaseCommand):
    """The Django command class for the restat command."""
    help = "Recalculates the stats"

    def add_arguments(self, parser):
        parser.add_argument("-f", "--force",
                            action="store_true",
                            dest="force",
                            default=False,
                            help="Force calculation even if no new Encounters")

    def handle(self, *args, **options):
        with single_process("restat"):
            start = time()
            start_date = datetime.now(timezone.utc)
            pruned_count = delete_old_files()
            forced = "force" in options and options["force"]
            last_run = datetime.fromtimestamp(0, timezone.utc) if forced else last_restat()
            era_count, area_count, user_count, new_encounter_count = calculate_stats(last_run, **options)
            end = time()
            end_date = datetime.now(timezone.utc)

            if options["verbosity"] >= 1:
                print()
                print("Completed in %ss" % (end - start))

            if (new_encounter_count + pruned_count) > 0:
                RestatPerfStats.objects.create(
                    started_on=start_date,
                    ended_on=end_date,
                    number_users=user_count,
                    number_eras=era_count,
                    number_areas=area_count,
                    number_new_encounters=new_encounter_count,
                    number_pruned_evtcs=pruned_count,
                    was_force=forced)


def _merge_slice(data, data_slice):
    for key, val in list(data_slice.items()):
        if isinstance(val, dict):
            if key not in data:
                data[key] = {}
            _merge_slice(data[key], data_slice[key])
        else:
            if key == "count":
                if key not in data:
                    data[key] = 0
                data[key] = max(data[key], val)
            else:
                if key not in data:
                    data[key] = []
                data[key].append(val)


def _foreach_value(map_func, data, **kwargs):
    for key, val in list(data.items()):
        if isinstance(val, dict):
            _foreach_value(map_func, data[key], **kwargs)
        else:
            map_func(key, data, **kwargs)


def _summarize_slice(key, data, **kwargs):
    if str(key).startswith("total"):
        data[key] = sum(data[key])
    elif key != "count":
        data[key] = sum(data[key]) / kwargs["encounter_duration"]


def _summarize_area(key, data, **kwargs):  # pylint: disable=unused-argument
    if key != "count":
        val = data.pop(key)
        val.sort()
        length = len(val)
        percent_length = length / 100
        data["min_" + key] = val[0]
        data["max_" + key] = val[-1]
        data["avg_" + key] = sum(val) / length
        data["per_" + key] = base64.b64encode(numpy.array([val[floor(i * percent_length)] for i in range(0, 100)],
                                                          dtype=numpy.float32).tobytes()).decode("utf-8")


def _summarize_user(key, data, **kwargs):  # pylint: disable=unused-argument
    if key != "count":
        val = data.pop(key)
        if key not in ["down_percentage", "dead_percentage", "disconnect_percentage"]:
            val.sort()
            data["min_" + key] = val[0]
            data["max_" + key] = val[-1]
            data["avg_" + key] = sum(val) / len(val)
        else:
            data["avg_" + key] = 100.0 * sum(val) / len(val)


def _increment_buff_stats(source_data, target_data, targets, phase_duration, relative=False):
    for target in targets:
        for buff, uptime in source_data[target].items():
            if buff not in target_data[target]:
                target_data[target][buff] = []
            target_data[target][buff].append(uptime if not relative else uptime * phase_duration)


def _increment_area_general_stats(source_data, target_data, phase_duration, relative=False):
    if "duration" not in target_data:
        target_data["duration"] = []
    target_data["duration"].append(phase_duration)

    for target in ALL_STATS:
        prefix = target.split("_")[0]
        suffix = target.split("_")[-1]
        # Pseudo switch
        # https://stackoverflow.com/questions/60208/replacements-for-switch-statement-in-python
        source = {
            "boss": source_data["actual_boss"],
            "shielded": source_data["shielded"],
            "received": source_data["received"],
            "default": source_data["actual"],
        }
        source = source.get(suffix, source["default"])
        if target not in target_data:
            target_data[target] = []
        target_data[target].append(source[prefix] if not relative or prefix == "total"
                                   else source[prefix] * phase_duration)


def _increment_user_general_stats(source_data, target_data, phase_duration):
    for target in ["down", "dead", "disconnect"]:
        if target + "_percentage" not in target_data:
            target_data[target + "_percentage"] = []
        target_data[target + "_percentage"].append(source_data["events"][target + "_time"] / phase_duration)

    _increment_area_general_stats(source_data, target_data, phase_duration)


def _update_area_leaderboards(area_leaderboards, encounter, squad_slice):
    if encounter.success:
        if encounter.week() not in area_leaderboards:
            area_leaderboards["periods"][encounter.week()] = {"duration": []}
        leaderboard_item = {
            "id": encounter.id,
            "url_id": encounter.url_id,
            "duration": encounter.duration,
            "dps_boss": squad_slice["dps_boss"],
            "dps": squad_slice["dps"],
            "buffs": {buff: uptimes for buff, uptimes in squad_slice["buffs"].items()},
            "comp": [[p.archetype, p.profession, p.elite] for p in encounter.participations.all()],
            "tags": encounter.tagstring,
        }

        for target in ["Era", encounter.week()]:
            area_leaderboards["periods"][target]["duration"].append(leaderboard_item)
            area_leaderboards["periods"][target]["duration"] = sorted(area_leaderboards["periods"][target]["duration"],
                                                                      key=lambda x: x["duration"])[:10]
        area_leaderboards["max_max_dps"] = max(area_leaderboards["max_max_dps"], leaderboard_item["dps"])


def _generate_player_data(player, phase, phase_duration):
    player_data = player.data()
    player_data["actual"] = EncounterDamage.breakdown(phase.encounterdamage_set.filter(source=player.character,
                                                                                       target="*All", damage__gt=0),
                                                      phase_duration, group=True)
    player_data["actual_boss"] = EncounterDamage.breakdown(phase.encounterdamage_set
                                                           .filter(source=player.character, target="*Boss",
                                                                   damage__gt=0),
                                                           phase_duration, group=True)
    player_data["received"] = EncounterDamage.breakdown(phase.encounterdamage_set
                                                        .filter(target=player.character, damage__gt=0),
                                                        phase_duration, group=True)
    player_data["shielded"] = EncounterDamage.breakdown(phase.encounterdamage_set
                                                        .filter(target=player.character, damage__lt=0),
                                                        phase_duration, group=True, absolute=True)
    player_data["buffs"] = EncounterBuff.breakdown(phase.encounterbuff_set.filter(target=player.character))
    player_data["buffs_out"] = EncounterBuff.breakdown(phase.encounterbuff_set
                                                       .filter(source=player.character), use_sum=True)

    player_data["events"] = EncounterEvent.summarize(phase.encounterevent_set.filter(source=player.character))

    return player_data


def _generate_squad_data(players_data):

    squad_data = {
        "actual": {},
        "actual_boss": {},
        "received": {},
        "shielded": {},
        "buffs": {},
    }

    for player_data in players_data:
        for target in squad_data:
            for key, val in player_data[target].items():
                if key not in squad_data[target]:
                    squad_data[target][key] = []
                squad_data[target][key].append(val)

    for target in squad_data:
        for key, val in squad_data[target].items():
            squad_data[target][key] = sum(squad_data[target][key]) if target != "buffs"\
                else sum(squad_data[target][key]) / len(squad_data[target][key])

    return squad_data


def _update_phase(encounter, phase, players_data, squad_data, area_store, merge=False, relative=False):
    phase_duration = encounter.calc_phase_duration(phase)
    if phase.name not in area_store:
        area_store[phase.name] = {"group": {"count": 0, "buffs": {}, "buffs_out": {}},
                                  "individual": {"count": 0},
                                  "build": {"All": {"All": {"All": {"count": 0, "buffs": {}, "buffs_out": {}}}}}}
    phase_store = area_store["All"] if merge else area_store[phase.name]
    for player_data in players_data:
        # Individual data
        # Other stats
        _increment_area_general_stats(player_data, phase_store["individual"], phase_duration, relative=relative)
        # Increase member count
        phase_store["individual"]["count"] += 1

        # Build data
        arch = player_data["archetype"]
        prof = player_data["profession"]
        elite = player_data["elite"]
        if arch not in phase_store["build"]:
            phase_store["build"][arch] = {"All": {"All": {"count": 0, "buffs": {}, "buffs_out": {}}}}
        if prof not in phase_store["build"][arch]:
            phase_store["build"][arch][prof] = {"All": {"count": 0, "buffs": {}, "buffs_out": {}}}
        if elite not in phase_store["build"][arch][prof]:
            phase_store["build"][arch][prof][elite] = {"count": 0, "buffs": {}, "buffs_out": {}}

        for target_store in [phase_store["build"]["All"]["All"]["All"],
                             phase_store["build"][arch]["All"]["All"],
                             phase_store["build"][arch][prof]["All"],
                             phase_store["build"][arch][prof][elite]]:
            # Buffs
            _increment_buff_stats(player_data, target_store, ["buffs", "buffs_out"], phase_duration, relative=relative)
            # Other stats
            _increment_area_general_stats(player_data, target_store, phase_duration, relative=relative)
            # Increase build count
            target_store["count"] += 1

    # Squad data
    # Buffs
    _increment_buff_stats(squad_data, phase_store["group"], ["buffs"], phase_duration, relative=relative)
    # Other stats
    _increment_area_general_stats(squad_data, phase_store["group"], phase_duration, relative=relative)
    # Increase squad count
    phase_store["group"]["count"] += 1


def _recalculate_area(era, area, era_store):
    area_store = copy.deepcopy(DEFAULT_AREA_STORE)
    if area.id not in era_store:
        era_store[area.id] = copy.deepcopy(DEFAULT_AREA_STORE)
    area_leaderboards = {"periods": {"Era": {"duration": []}}, "max_max_dps": 0}
    for encounter in era.encounters.filter(area_id=area):
        area_slice = copy.deepcopy(DEFAULT_AREA_STORE)
        for phase in encounter.encounter_data.encounterphase_set.all():
            # Pregenerate player data
            phase_duration = encounter.calc_phase_duration(phase)
            players_data = [_generate_player_data(player, phase, phase_duration)
                            for player in encounter.encounter_data.encounterplayer_set.all()]
            squad_data = _generate_squad_data(players_data)
            # Update phase
            _update_phase(encounter, phase, players_data, squad_data, area_store)
            _update_phase(encounter, phase, players_data, squad_data, era_store[area.id])
            # Update area slice for "All" phase
            _update_phase(encounter, phase, players_data, squad_data, area_slice, merge=True, relative=True)

        # Generate "All" phase from area slice
        _foreach_value(_summarize_slice, area_slice, encounter_duration=encounter.duration)
        _merge_slice(area_store["All"], area_slice["All"])
        _merge_slice(era_store[area.id]["All"], area_slice["All"])

        _update_area_leaderboards(area_leaderboards, encounter, area_slice["All"]["group"])

    _foreach_value(_summarize_area, area_store)
    EraAreaStore.objects.update_or_create(era=era, area_id=area.id, defaults={"val": area_store,
                                                                              "leaderboards": area_leaderboards})


def _recalculate_users(era, user):
    user_data = {"encounter": {"All raid bosses": {"All": {"All": {"All": {"count": 0,
                                                                           "buffs": {},
                                                                           "buffs_out": {}}}}}}}
    for encounter in era.encounters.filter(participations__account__user=user):
        data = encounter.encounter_data
        for player in EncounterPlayer.objects.filter(account__in=user.accounts.all(), encounter_data=data):
            arch = player.archetype
            prof = player.profession
            elite = player.elite

            # Generate player data
            player_data = _generate_player_data(player, data, encounter.duration)

            for target in ["All raid bosses", encounter.area_id]:
                if target not in user_data["encounter"]:
                    user_data["encounter"][target] = {"All": {"All": {"All": {"count": 0,
                                                                              "buffs": {},
                                                                              "buffs_out": {}}}}}
                if arch not in user_data["encounter"][target]:
                    user_data["encounter"][target][arch] = {"All": {"All": {"count": 0, "buffs": {}, "buffs_out": {}}}}
                if prof not in user_data["encounter"][target][arch]:
                    user_data["encounter"][target][arch][prof] = {"All": {"count": 0, "buffs": {}, "buffs_out": {}}}
                if elite not in user_data["encounter"][target][arch][prof]:
                    user_data["encounter"][target][arch][prof][elite] = {"count": 0, "buffs": {}, "buffs_out": {}}
                if prof not in user_data["encounter"][target]["All"]:
                    user_data["encounter"][target]["All"][prof] = {}
                if elite not in user_data["encounter"][target]["All"][prof]:
                    user_data["encounter"][target]["All"][prof][elite] = {"count": 0, "buffs": {}, "buffs_out": {}}
                user_area_data = user_data["encounter"][target]

                for prv_target in [
                        user_area_data["All"]["All"]["All"],
                        user_area_data[arch]["All"]["All"],
                        user_area_data[arch][prof]["All"],
                        user_area_data[arch][prof][elite],
                ]:
                    # Buffs
                    _increment_buff_stats(player_data, prv_target, ["buffs_out"], encounter.duration)
                    # Other stats
                    _increment_user_general_stats(player_data, prv_target, encounter.duration * 1000.0)
                    # Increase build count
                    prv_target["count"] += 1

    _foreach_value(_summarize_user, user_data)
    EraUserStore.objects.update_or_create(era=era, user_id=user.id, defaults={"val": user_data})


def recalculate_era(era, encounters):
    """Extracts all modified Area and User models from the supplied Encounter group and initiates their recalculation"""
    era_data = {}
    areas = Area.objects.filter(encounters__in=encounters)
    users = User.objects.filter(accounts__encounters__in=encounters)

    for area in areas:
        _recalculate_area(era, area, era_data)
    for user in users:
        _recalculate_users(era, user)

    _foreach_value(_summarize_area, era_data)
    era.val = era_data
    return len(areas), len(users)


def calculate_stats(last_run, **options):
    """Fetches all new Encounters from the database, groups them by Era and
    calls <code>recalculate_era</code> for every group."""
    era_count = 0
    area_count = 0
    user_count = 0
    encounter_count = 0
    for era in Era.objects.all():
        era_count += 1
        encounters = Encounter.objects.filter(era=era, uploaded_on__gte=last_run)
        if encounters:
            encounter_count = len(encounters)
            area_count, user_count = recalculate_era(era, encounters)
        elif options["verbosity"] >= 2:
            print("Skipped era %s" % era)
    return era_count, area_count, user_count, encounter_count
