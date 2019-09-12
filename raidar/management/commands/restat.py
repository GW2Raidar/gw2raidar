"""
Raidar ReStat
=============

Offers a Django command to recalculate the distribution of encounter-related performance stats by analyzing all
new encounter logs and generating or updating any related percentile blobs.
"""

from contextlib import contextmanager
from datetime import timezone
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
    Area, EncounterDamage, EncounterBuff


# DEBUG: uncomment to log SQL queries
# import logging
# l = logging.getLogger("django.db.backends")
# l.setLevel(logging.DEBUG)
# l.addHandler(logging.StreamHandler())

AVG_STATS = ["crit", "flanking", "scholar", "seaweed"]
SUM_STATS = ["dps", "dps_boss", "dps_received", "total_shielded", "total_received"]
ALL_STATS = AVG_STATS + SUM_STATS


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


def _foreach_value(data, map_func):
    for key, val in list(data.items()):
        if isinstance(val, dict):
            _foreach_value(val, map_func)
        else:
            map_func(data, key)


def _summarize_area(data, key):
    if key != "count":
        val = data.pop(key)
        val.sort()
        data["min_" + key] = val[0]
        data["max_" + key] = val[-1]
        data["avg_" + key] = sum(val) / len(val)
        data["per_" + key] = base64.b64encode(numpy.percentile(val, range(0, 100)).astype(numpy.float32).tobytes())\
            .decode("utf-8")


def _summarize_user(data, key):
    if key != "count":
        val = data.pop(key)
        if key not in ["down_percentage", "dead_percentage", "disconnect_percentage"]:
            val.sort()
            data["min_" + key] = val[0]
            data["max_" + key] = val[-1]
            data["avg_" + key] = sum(val) / len(val)
        else:
            data["avg_" + key] = 100.0 * sum(val) / len(val)


def _increment_buff_stats(source_data, target_data, targets):
    for target in targets:
        for buff, uptime in source_data[target].items():
            if buff not in target_data[target]:
                target_data[target][buff] = [0] * target_data["count"]
            target_data[target][buff].append(uptime)


def _increment_area_general_stats(source_data, target_data, duration):
    if "duration" not in target_data:
        target_data["duration"] = []
    target_data["duration"].append(duration)

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
        target_data[target].append(source[prefix])


def _increment_user_general_stats(source_data, target_data, duration):
    for target in ["down", "dead", "disconnect"]:
        if target + "_percentage" not in target_data:
            target_data[target + "_percentage"] = []
        target_data[target + "_percentage"].append(source_data["events"][target + "_time"] / duration)

    _increment_area_general_stats(source_data, target_data, duration)


def _find_player_data(accounts, dump, phase="All"):
    if phase in dump["encounter"]["phases"]:
        for party in dump["encounter"]["phases"][phase]["parties"].values():
            for member in party["members"]:
                if member["account"] in accounts:
                    return member
    return None


def _merge_into_squad_store(squad_store, build_store, squad_size, duration):
    if "duration" not in squad_store:
        squad_store["duration"] = []
    squad_store["duration"].append(duration)

    # Buffs
    for target in ["buffs", "buffs_out"]:
        for buff, uptimes in build_store[target]:
            if buff not in squad_store[target]:
                squad_store[target][buff] = [0] * squad_store["count"]
            stat_sum = sum(uptimes[-squad_size:])
            if target == "buffs":
                squad_store[target][buff].append(stat_sum / squad_size)
            else:
                squad_store[target][buff].append(stat_sum)

    # Other stats
    for target in ALL_STATS:
        if target not in squad_store:
            squad_store[target] = []
        stat_sum = sum(build_store[target][-squad_size:])
        if target in AVG_STATS:
            squad_store[target].append(stat_sum / squad_size)
        else:
            squad_store[target].append(stat_sum)


def _update_area_leaderboards(area_leaderboards, encounter, squad_store):
    if encounter.success:
        if encounter.week() not in area_leaderboards:
            area_leaderboards["periods"][encounter.week()] = {"duration": []}
        leaderboard_item = {
            "id": encounter.id,
            "url_id": encounter.url_id,
            "duration": encounter.duration,
            "dps_boss": squad_store["dps_boss"][-1],
            "dps": squad_store["dps"][-1],
            "buffs": {buff: uptimes[-1] for buff, uptimes in squad_store["buff"].items()},
            "comp": [[p.archetype, p.profession, p.elite] for p in encounter.participations.all()],
            "tags": encounter.tagstring,
        }

        for target in ["Era", encounter.week()]:
            area_leaderboards["periods"][target]["duration"].append(leaderboard_item)
            area_leaderboards["periods"][target]["duration"] = sorted(area_leaderboards["periods"][target]["duration"],
                                                                      key=lambda x: x["duration"])[:10]
        area_leaderboards["max_max_dps"] = max(area_leaderboards["max_max_dps"], leaderboard_item["dps"])


def _recalculate_area(era, area, era_data):
    area_store = {"All": {"group": {"count": 0, "buffs": {}, "buffs_out": {}},
                          "individual": {"count": 0},
                          "build": {"All": {"All": {"All": {"count": 0, "buffs": {}, "buffs_out": {}}}}}}}
    area_leaderboards = {"periods": {"Era": {"duration": []}}, "max_max_dps": 0}
    for encounter in era.encounters.filter(area_id=area):
        data = encounter.encounter_data
        for phase in data.encounterphase_set:
            phase_duration = encounter.calc_phase_duration(phase)
            if phase.name not in area_store:
                area_store[phase.name] = {"group": {"count": 0, "buffs": {}, "buffs_out": {}},
                                          "individual": {"count": 0},
                                          "build": {"All": {"All": {"All": {"count": 0,
                                                                            "buffs": {},
                                                                            "buffs_out": {}}}}}}
            ind_store = area_store[phase.name]["individual"]
            build_store = area_store[phase.name]["build"]
            squad_store = area_store[phase.name]["group"]
            for party_name in phase.encounterplayer_set.values_list("party").distinct():
                for player in phase.encounterplayer_set.filter(party=party_name):
                    # Generate player data
                    player_data = player.data()
                    player_data["actual"] = EncounterDamage.breakdown(phase.encounterdamage_set
                                                                      .filter(source=player.character,
                                                                              target="*All",
                                                                              damage__gt=0),
                                                                      phase.duration, group=True)
                    player_data["actual_boss"] = EncounterDamage.breakdown(phase.encounterdamage_set
                                                                           .filter(source=player.character,
                                                                                   target="*Boss",
                                                                                   damage__gt=0),
                                                                           phase.duration, group=True)
                    player_data["received"] = EncounterDamage.breakdown(phase.encounterdamage_set
                                                                        .filter(target=player.character, damage__gt=0),
                                                                        phase.duration, group=True)
                    player_data["shielded"] = EncounterDamage.breakdown(phase.encounterdamage_set
                                                                        .filter(target=player.character, damage__lt=0),
                                                                        phase_duration, group=True, absolute=True)
                    player_data["buffs"] = EncounterBuff.breakdown(phase.encounterbuff_set
                                                                   .filter(target=player.character))
                    player_data["buffs_out"] = EncounterBuff.breakdown(phase.encounterbuff_set
                                                                       .filter(source=player.character), use_sum=True)

                    # Individual data
                    # Other stats
                    _increment_area_general_stats(player_data, ind_store, phase_duration)
                    # Increase member count
                    ind_store["count"] += 1

                    # Build data
                    arch = player_data["archetype"]
                    prof = player_data["profession"]
                    elite = player_data["elite"]
                    if arch not in area_store[phase.name]["build"]:
                        area_store[phase.name]["build"][arch] = {"All": {"All": {"count": 0,
                                                                                 "buffs": {},
                                                                                 "buffs_out": {}}}}
                    if prof not in area_store[phase.name]["build"][arch]:
                        area_store[phase.name]["build"][arch][prof] = {"All": {"count": 0,
                                                                               "buffs": {},
                                                                               "buffs_out": {}}}
                    if elite not in area_store[phase.name]["build"][arch][prof]:
                        area_store[phase.name]["build"][arch][prof][elite] = {"count": 0, "buffs": {}, "buffs_out": {}}
                    if prof not in area_store[phase.name]["build"]["All"]:
                        area_store[phase.name]["build"]["All"][prof] = {}
                    if elite not in area_store[phase.name]["build"]["All"][prof]:
                        area_store[phase.name]["build"]["All"][prof][elite] = {"count": 0, "buffs": {}, "buffs_out": {}}

                    for target_store in [build_store["All"]["All"]["All"],
                                         build_store[arch]["All"]["All"],
                                         build_store["All"][prof][elite],
                                         build_store[arch][prof]["All"],
                                         build_store[arch][prof][elite]]:
                        # Buffs
                        _increment_buff_stats(player_data, target_store, ["buffs", "buffs_out"])
                        # Other stats
                        _increment_area_general_stats(player_data, target_store, phase_duration)
                        # Increase build count
                        target_store["count"] += 1

            # Squad data
            _merge_into_squad_store(squad_store, build_store["All"]["All"]["All"], phase.encounterplayer_set.count(),
                                    phase_duration)
            # Increase squad count
            squad_store["count"] += 1

        # TODO: "All" phase
        # TODO: Update era data

        _update_area_leaderboards(area_leaderboards, encounter, area_store["All"]["group"])

    _foreach_value(area_store, _summarize_area)
    EraAreaStore.objects.update_or_create(era=era, area_id=area.id, defaults={"val": area_store,
                                                                              "leaderboards": area_leaderboards})


# TODO: Rebuild with database ops
def _recalculate_users(era, user):
    user_data = {"encounter": {"All raid bosses": {"All": {"All": {"All": {"count": 0,
                                                                           "buffs": {},
                                                                           "buffs_out": {}}}}}}}
    encounters = era.encounters.filter(participations__account__user=user)
    for encounter in encounters:
        player_data = _find_player_data([account.name for account in user.accounts.all()], encounter.json_dump())
        if player_data is not None:
            arch = player_data["archetype"]
            prof = player_data["profession"]
            elite = player_data["elite"]

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

                for prv_target in [user_area_data["All"]["All"]["All"],
                                   user_area_data[arch]["All"]["All"],
                                   user_area_data["All"][prof][elite],
                                   user_area_data[arch][prof]["All"],
                                   user_area_data[arch][prof][elite],
                                   ]:
                    # Buffs
                    _increment_buff_stats(player_data, prv_target, ["buffs_out"])
                    # Other stats
                    _increment_user_general_stats(player_data, prv_target, encounter.duration * 1000)
                    # Increase build count
                    prv_target["count"] += 1

    _foreach_value(user_data, _summarize_user)
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

    _foreach_value(era_data, _summarize_area)
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
