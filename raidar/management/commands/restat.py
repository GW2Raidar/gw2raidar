"""
Raidar ReStat
=============

Offers a Django command to recalculate the distribution of encounter-related performance stats by analyzing all
new encounter logs and generating or updating any related percentile blobs.
"""

from contextlib import contextmanager
from time import time
import os
import sys
import base64
import numpy
import psutil
from django.core.management.base import BaseCommand
from django.db.utils import IntegrityError
from raidar.models import Variable, Encounter, RestatPerfStats, EraAreaStore, EraUserStore, Era, settings, datetime

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
        pid_var = Variable.objects.create(key="%s_pid" % name, val=os.getpid())
        try:
            yield pid
        finally:
            pid_var.delete()
    except IntegrityError:
        # Already running
        sys.exit()


# TODO: Replace with RestatPerfStats check
@contextmanager
def necessary():
    """Determines the timespan since the last restat run and updates the value after completion."""
    try:
        last_run = Variable.get("restat_last")
    except Variable.DoesNotExist:
        last_run = 0

    start = time()

    yield last_run

    # Only if successful:
    Variable.set("restat_last", start)


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


# TODO: Create db models for restat results (If necessary)
# TODO: Rebuild restat for new db layout (If necessary)
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
        with single_process("restat"), necessary() as last_run:
            start = time()
            start_date = datetime.now()
            pruned_count = delete_old_files()
            era_count, area_count, user_count, new_encounter_count = calculate_stats(last_run, **options)
            end = time()
            end_date = datetime.now()

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
                    was_force=options["force"])


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


def _increment_area_buff_stats(source_data, target_data):
    for target in ["buffs", "buffs_out"]:
        for buff, uptime in source_data[target]:
            if buff not in target_data[target]:
                target_data[target][buff] = [0] * (target_data["count"] - 1)
            target_data[target][buff].append(uptime)


def _increment_area_general_stats(source_data, target_data):
    if "duration" not in target_data:
        target_data["duration"] = [0] * (target_data["count"] - 1)
    target_data["duration"].append(source_data["duration"])

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


def _increment_user_buff_stats(source_data, target_data):
    for buff, uptime in source_data["buffs_out"]:
        if buff not in target_data["outgoing"]:
            target_data["outgoing"][buff] = [0] * (target_data["count"] - 1)
        target_data["outgoing"][buff].append(uptime)


def _increment_user_general_stats(source_data, target_data):
    for target in ["down", "dead", "disconnect"]:
        if target + "_percentage" not in target_data:
            target_data[target + "_percentage"] = [0] * (target_data["count"] - 1)
        target_data[target + "_percentage"].append(source_data["events"][target + "_time"] / source_data["duration"])

    _increment_area_general_stats(source_data, target_data)


def _find_player_data(accounts, dump, phase="All"):
    if phase in dump["encounter"]["phases"]:
        for member in dump["encounter"]["phases"][phase]["members"]:
            if member["account"] in accounts:
                return member
    return None


def _update_area_leaderboards(area_leaderboards, encounter, dump):
    if encounter.success:
        if encounter.week() not in area_leaderboards:
            area_leaderboards[encounter.week()] = {"duration": []}
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
            area_leaderboards[target]["duration"].append(leaderboard_item)
            area_leaderboards[target]["duration"] = sorted(area_leaderboards[target], key=lambda x: x["duration"])[:10]
        area_leaderboards["max_max_dps"] = max(area_leaderboards["max_max_dps"], leaderboard_item["dps"])


def _recalculate_area(era, area):
    area_data = {}
    area_leaderboards = {"Era": {"duration": []}, "max_max_dps": 0}
    for encounter in era.encounter_set.filter(area_id=area):
        dump = encounter.json_dump()
        for phase_name in dump["encounter"]["phases"]:
            if phase_name not in area_data:
                area_data[phase_name] = {"group": {"count": 0, "buffs": {}, "buffs_out": {}},
                                         "individual": {"count": 0},
                                         "build": {}}

            # Party data
            for party_data in dump["encounter"]["phases"][phase_name]["parties"].values():
                area_group_data = area_data[phase_name]["group"]

                # Buffs
                _increment_area_buff_stats(party_data, area_group_data)
                # Other stats
                _increment_area_general_stats(party_data, area_group_data)
                # Increase group count
                area_group_data["count"] += 1

                # Individual data
                area_ind_data = area_data[phase_name]["individual"]
                for member_data in party_data["members"]:

                    # Other stats
                    _increment_area_general_stats(member_data, area_ind_data)
                    # Increase member count
                    area_ind_data["count"] += 1

                    # Build data
                    prof = member_data["profession"]
                    elite = member_data["elite"]
                    archetype = member_data["archetype"]
                    if prof not in area_data[phase_name]["build"]:
                        area_data[phase_name]["build"][prof] = {}
                    if elite not in area_data[phase_name]["build"][prof]:
                        area_data[phase_name]["build"][prof][elite] = {}
                    if archetype not in area_data[phase_name]["build"][prof][elite]:
                        area_data[phase_name]["build"][prof][elite][archetype] = {"count": 0,
                                                                                  "buffs": {},
                                                                                  "buffs_out": {}}
                    area_build_data = area_data[phase_name]["build"][prof][elite][archetype]

                    # Buffs
                    _increment_area_buff_stats(member_data, area_build_data)
                    # Other stats
                    _increment_area_general_stats(member_data, area_build_data)
                    # Increase build count
                    area_build_data["count"] += 1
                    # TODO: Do we need class->elite->"All"?
                    # TODO: Do we need "All"->"All"->archetype?

        _update_area_leaderboards(area_leaderboards, encounter, dump)

    _foreach_value(area_data, _summarize_area)
    EraAreaStore.objects.update_or_create(era=era, area_id=area.id, defaults={"val": area_data,
                                                                              "leaderboards": area_leaderboards})


# TODO: Rebuild user data output to match area data
def _recalculate_users(era, user):
    user_data = {"count": 0, "encounter": {}, "summary": {}}
    for encounter in era.encounter_set.filter(participation__account__in=user.account_set):
        player_data = _find_player_data([account.name for account in user.account_set], encounter.json_dump())
        if player_data is not None:
            prof = player_data["profession"]
            elite = player_data["elite"]
            archetype = player_data["archetype"]
            if encounter.area_id not in user_data["encounter"]:
                user_data["encounter"] = {"count": 0, "archetype": {}}
            if archetype not in user_data["encounter"][encounter.area_id]["archetype"]:
                user_data["encounter"][encounter.area_id]["archetype"][archetype] = {"profession": {}}
            if prof not in user_data["encounter"][encounter.area_id]["archetype"][archetype]["profession"]:
                user_data["encounter"][encounter.area_id]["archetype"][archetype]["profession"][prof] = {"elite": {}}
            if elite not in \
                    user_data["encounter"][encounter.area_id]["archetype"][archetype]["profession"][prof]["elite"]:
                user_data["encounter"][encounter.area_id]["archetype"][archetype]["profession"][prof]["elite"][elite] =\
                    {"count": 0, "outgoing": {}}
            area_build_data =\
                user_data["encounter"][encounter.area_id]["archetype"][archetype]["profession"][prof]["elite"][elite]

            # Buffs
            _increment_user_buff_stats(player_data, area_build_data)
            # Other stats
            _increment_user_general_stats(player_data, area_build_data)
            # Increase encounter count
            user_data["count"] += 1
            # TODO: Do we need archetype->"All"->"All"?
            # TODO: Do we need archetype->prof->"All"?
            # TODO: Do we need "All"->"All"->"All"?
            # TODO: Do we need "All raid bosses"?

    _foreach_value(user_data, _summarize_user)
    EraUserStore.objects.update_or_create(era=era, user_id=user.id, defaults={"val": user_data})


def recalculate_era(era, encounters):
    """Extracts all modified Area and User models from the supplied Encounter group and initiates their recalculation"""
    areas = encounters.area_set.distinct()
    users = encounters.accounts.user.distinct()

    for area in areas:
        _recalculate_area(era, area)
    for user in users:
        _recalculate_users(era, user)

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
        force_recalculation = "force" in options and options["force"]
        last_run_timestamp = 0 if force_recalculation else last_run
        encounters = Encounter.objects.filter(era=era, uploaded_at__gte=last_run_timestamp)
        if encounters:
            encounter_count = len(encounters)
            area_count, user_count = recalculate_era(era, encounters)
        elif options["verbosity"] >= 2:
            print("Skipped era %s" % era)
    return era_count, area_count, user_count, encounter_count
