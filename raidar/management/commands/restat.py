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
    Area


# DEBUG: uncomment to log SQL queries
# import logging
# l = logging.getLogger("django.db.backends")
# l.setLevel(logging.DEBUG)
# l.addHandler(logging.StreamHandler())


@contextmanager
def single_process(name):
    """Locks this module to prevent parallel runs, or exit if already locked."""
    try:
        pid = os.getpid()
        # TODO: This is very inconvenient!
        # Uncomment to remove pid in case of having cancelled restat with Ctrl+C...
        # Variable.objects.get(key="%s_pid" % name).delete()
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
                target_data[target][buff] = [0] * (target_data["count"] - 1)
            target_data[target][buff].append(uptime)


def _increment_area_general_stats(source_data, target_data, duration):
    if "duration" not in target_data:
        target_data["duration"] = [0] * (target_data["count"] - 1)
    target_data["duration"].append(duration)

    for target in ["crit", "dps", "dps_boss", "dps_received", "flanking", "scholar", "seaweed", "total_shielded",
                   "total_received"]:
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
            target_data[target] = [0] * (target_data["count"] - 1)
        target_data[target].append(source[prefix])


def _increment_user_general_stats(source_data, target_data, duration):
    for target in ["down", "dead", "disconnect"]:
        if target + "_percentage" not in target_data:
            target_data[target + "_percentage"] = [0] * (target_data["count"] - 1)
        target_data[target + "_percentage"].append(source_data["events"][target + "_time"] / duration)

    _increment_area_general_stats(source_data, target_data, duration)


def _find_player_data(accounts, dump, phase="All"):
    if phase in dump["encounter"]["phases"]:
        for party in dump["encounter"]["phases"][phase]["parties"].values():
            for member in party["members"]:
                if member["account"] in accounts:
                    return member
    return None


def _update_area_leaderboards(area_leaderboards, encounter, dump):
    if encounter.success:
        if encounter.week() not in area_leaderboards:
            area_leaderboards["periods"][encounter.week()] = {"duration": []}
        leaderboard_item = {
            "id": encounter.id,
            "url_id": encounter.url_id,
            "duration": encounter.duration,
            "dps_boss": dump["encounter"]["phases"]["All"]["actual_boss"]["dps"],
            "dps": dump["encounter"]["phases"]["All"]["actual_boss"]["dps"],
            "buffs": dump["encounter"]["phases"]["All"]["buffs"],
            "comp": [[p.archetype, p.profession, p.elite] for p in encounter.participations.all()],
            "tags": encounter.tagstring,
        }

        for target in ["Era", encounter.week()]:
            area_leaderboards["periods"][target]["duration"].append(leaderboard_item)
            area_leaderboards["periods"][target]["duration"] = sorted(area_leaderboards["periods"][target]["duration"],
                                                                      key=lambda x: x["duration"])[:10]
        area_leaderboards["max_max_dps"] = max(area_leaderboards["max_max_dps"], leaderboard_item["dps"])


# TODO: Rebuild with database ops
def _recalculate_area(era, area, era_data):
    area_data = {}
    area_leaderboards = {"periods": {"Era": {"duration": []}}, "max_max_dps": 0}
    for encounter in era.encounters.filter(area_id=area):
        dump = encounter.json_dump()
        for phase_name in dump["encounter"]["phases"]:
            phase_duration = dump["encounter"]["phases"][phase_name]["duration"]
            for target in [area_data, era_data]:
                if phase_name not in target:
                    target[phase_name] = {"group": {"count": 0, "buffs": {}, "buffs_out": {}},
                                          "individual": {"count": 0},
                                          "build": {"All": {"All": {"All": {"count": 0,
                                                                            "buffs": {},
                                                                            "buffs_out": {}}}}}}
                # Party data
                for party_data in dump["encounter"]["phases"][phase_name]["parties"].values():
                    group_data = target[phase_name]["group"]

                    # Buffs
                    _increment_buff_stats(party_data, group_data, ["buffs", "buffs_out"])
                    # Other stats
                    _increment_area_general_stats(party_data, group_data, phase_duration)
                    # Increase group count
                    group_data["count"] += 1

                    # Individual data
                    ind_data = target[phase_name]["individual"]
                    for member_data in party_data["members"]:

                        # Other stats
                        _increment_area_general_stats(member_data, ind_data, phase_duration)
                        # Increase member count
                        ind_data["count"] += 1

                        # Build data
                        arch = member_data["archetype"]
                        prof = member_data["profession"]
                        elite = member_data["elite"]
                        if arch not in target[phase_name]["build"]:
                            target[phase_name]["build"][arch] = {"All": {"All": {"count": 0,
                                                                                 "buffs": {},
                                                                                 "buffs_out": {}}}}
                        if prof not in target[phase_name]["build"][arch]:
                            target[phase_name]["build"][arch][prof] = {"All": {"count": 0,
                                                                               "buffs": {},
                                                                               "buffs_out": {}}}
                        if elite not in target[phase_name]["build"][arch][prof]:
                            target[phase_name]["build"][arch][prof][elite] = {"count": 0, "buffs": {}, "buffs_out": {}}
                        if prof not in target[phase_name]["build"]["All"]:
                            target[phase_name]["build"]["All"][prof] = {}
                        if elite not in target[phase_name]["build"]["All"][prof]:
                            target[phase_name]["build"]["All"][prof][elite] = {"count": 0, "buffs": {}, "buffs_out": {}}
                        build_data = target[phase_name]["build"]

                        for prv_target in [build_data["All"]["All"]["All"],
                                           build_data[arch]["All"]["All"],
                                           build_data["All"][prof][elite],
                                           build_data[arch][prof]["All"],
                                           build_data[arch][prof][elite]]:
                            # Buffs
                            _increment_buff_stats(member_data, prv_target, ["buffs", "buffs_out"])
                            # Other stats
                            _increment_area_general_stats(member_data, prv_target, phase_duration)
                            # Increase build count
                            prv_target["count"] += 1

        _update_area_leaderboards(area_leaderboards, encounter, dump)

    _foreach_value(area_data, _summarize_area)
    EraAreaStore.objects.update_or_create(era=era, area_id=area.id, defaults={"val": area_data,
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
