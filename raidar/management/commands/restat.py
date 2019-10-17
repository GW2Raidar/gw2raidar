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
from typing import Iterable, Tuple
import numpy
import psutil
from pandas import DataFrame
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db.utils import IntegrityError
from raidar.models import Variable, Encounter, RestatPerfStats, Era, settings, datetime, Area, EncounterDamage,\
    EncounterBuff, EncounterPlayer, EncounterEvent, BuildStat, EncounterPhase, SquadStat

# DEBUG: uncomment to log SQL queries
# import logging
# l = logging.getLogger("django.db.backends")
# l.setLevel(logging.DEBUG)
# l.addHandler(logging.StreamHandler())

REMAP = {"actual": "cleave", "actual_boss": "target", "buffs_out": "buffs", "received": "target"}


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
            era_count, area_count, user_count, new_encounter_count = update_stats(last_run, **options)
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


def _modify_dict(dictionary: dict, prefix: str):
    return {prefix + str(key): val for key, val in dictionary.items()}


def _generate_statistics(frame: DataFrame):
    min_stats = frame.min()
    avg_stats = frame.mean()
    max_stats = frame.max()
    percentiles = frame.quantile(numpy.arange(0.01, 1.01, 0.01))

    return min_stats, avg_stats, max_stats, percentiles


def _generate_sum_statistics(frame: DataFrame, squad=False):
    frame = frame.copy()
    factors = frame.phase_duration / frame.encounter_duration
    rel_frame = frame.select_dtypes(include="number").drop(["encounter_duration", "phase_duration"], axis="columns")
    rel_frame = rel_frame[[col for col in rel_frame.columns if "dps" in col or "buff" in col]]
    rel_frame = rel_frame.mul(factors, axis="index")
    frame.update(rel_frame)
    sum_frame = frame.groupby(["encounter_id"] if squad else ["character_name", "encounter_id"]).sum()
    return _generate_statistics(sum_frame)


def _generate_squad_statistics(frame: DataFrame, sum=False):  # TODO: Fix for buffs (Incoming)
    frame = frame.copy()
    rel_frame = frame.select_dtypes(include="number")
    rel_frame = rel_frame[[col for col in rel_frame.columns if "buffs__" in col]]
    rel_frame /= frame.count()
    frame.update(rel_frame)
    avg_frame = frame.groupby(["encounter_id", "phase_name"] if sum else ["encounter_id"]).sum()
    return _generate_sum_statistics(avg_frame, squad=True) if sum else _generate_statistics(avg_frame)


def _generate_player_data(player: EncounterPlayer, phase: EncounterPhase, phase_duration: float):
    player_data = player.data()
    player_data["phase_name"] = phase.name
    player_data["phase_duration"] = phase_duration
    player_data["character_name"] = player.character
    player_data["encounter_id"] = phase.encounter_data.encounter.id
    player_data["area_id"] = player.encounter_data.encounter.area.id
    player_data["encounter_duration"] = phase.encounter_data.encounter.duration
    player_data.update(_modify_dict(EncounterDamage.breakdown(phase.encounterdamage_set.filter(source=player.character,
                                                                                               target="*All",
                                                                                               damage__gt=0),
                                                              phase_duration, group=True),
                                    prefix="actual__"))
    player_data.update(_modify_dict(EncounterDamage.breakdown(phase.encounterdamage_set
                                                              .filter(source=player.character, target="*Boss",
                                                                      damage__gt=0),
                                                              phase_duration, group=True),
                                    prefix="actual_boss__"))
    player_data.update(_modify_dict(EncounterDamage.breakdown(phase.encounterdamage_set
                                                              .filter(target=player.character, damage__gt=0),
                                                              phase_duration, group=True),
                                    prefix="received__"))
    player_data.update(_modify_dict(EncounterDamage.breakdown(phase.encounterdamage_set
                                                              .filter(target=player.character, damage__lt=0),
                                                              phase_duration, group=True, absolute=True),
                                    prefix="shielded__"))

    player_data.update(_modify_dict(EncounterBuff.breakdown(phase.encounterbuff_set.filter(target=player.character)),
                                    prefix="buffs__"))
    player_data.update(_modify_dict(EncounterBuff.breakdown(phase.encounterbuff_set.filter(source=player.character),
                                                            use_sum=True),
                                    prefix="buffs_out__"))

    player_data.update(_modify_dict(EncounterEvent.summarize(phase.encounterevent_set.filter(source=player.character)),
                                    prefix="events__"))

    return player_data


def _update_stats(era: Era, area: Area, phase_name: str, frame: DataFrame,
                  build: Tuple[int, int, int] = None):
    if build is None:
        min_stats, avg_stats, max_stats, percentiles = _generate_squad_statistics(frame, sum=phase_name == "All")
    else:
        if phase_name == "All":
            min_stats, avg_stats, max_stats, percentiles = _generate_sum_statistics(frame)
        else:
            min_stats, avg_stats, max_stats, percentiles = _generate_statistics(frame)

    for col in percentiles.columns:
        if "__" in col and min_stats[col] is not None:
            prefix, suffix = col.split("__", 1)
            out = prefix in ["actual", "actual_boss", "buffs_out"]
            prefix = REMAP.get(prefix, prefix)

            if build is None:
                stat = SquadStat.objects.get_or_create(era=era, area=area, phase=phase_name,
                                                       group=prefix, name=suffix, out=out)[0]
            else:
                stat = BuildStat.objects.get_or_create(era=era, area=area, phase=phase_name,
                                                       archetype=build[0], prof=build[1], elite=build[2], group=prefix,
                                                       name=suffix, out=out)[0]

            stat.min_val = min_stats[col]
            stat.avg_val = avg_stats[col]
            stat.max_val = max_stats[col]
            stat.perc_data = base64.b64encode(numpy.array(percentiles[col], dtype=numpy.float32)
                                              .tobytes()).decode("utf-8")
            stat.save()


def _update_area(era: Era, area: Area):
    raw_data = []
    # Load raw data from database
    for encounter in era.encounters.filter(area=area):
        for phase in encounter.encounter_data.encounterphase_set.all():
            phase_duration = encounter.calc_phase_duration(phase)
            for player in encounter.encounter_data.encounterplayer_set.all():
                raw_data.append(_generate_player_data(player, phase, phase_duration))
    frame = DataFrame(raw_data)

    # Update build stats
    for build, build_frame in frame.groupby(["archetype", "profession", "elite"]):
        for phase_name, phase_frame in build_frame.groupby("phase_name"):
            _update_stats(era, area, phase_name, phase_frame, build)
        _update_stats(era, area, "All", build_frame, build)

    # Update squad stats
    for phase_name, phase_frame in frame.groupby("phase_name"):
        _update_stats(era, area, phase_name, phase_frame)
    _update_stats(era, area, "All", frame)


def _update_user(era: Era, user: User):
    raw_data = []
    # Load raw data from database
    for encounter in Encounter.objects.filter(era=era, participations__account__in=user.accounts.all()):
        for phase in encounter.encounter_data.encounterphase_set.all():
            phase_duration = encounter.calc_phase_duration(phase)
            for player in encounter.encounter_data.encounterplayer_set.filter(account__in=user.accounts.all()):
                raw_data.append(_generate_player_data(player, phase, phase_duration))

    # Create pandas DataFrame
    frame = DataFrame(raw_data)
    for build, build_frame in frame.groupby(["archetype", "profession", "elite"]):
        for area_id, area_frame in build_frame.groupby("area_id"):
            area = Area.objects.get(id=area_id)
            _update_stats(era, area, "All", area_frame, build)


def update_era(era: Era, encounters: Iterable[Encounter]):
    """Extracts all modified Area and User models from the supplied Encounter group and initiates their recalculation"""
    areas = Area.objects.filter(encounters__in=encounters)
    users = User.objects.filter(accounts__encounters__in=encounters)

    for area in areas:
        _update_area(era, area)
    for user in users:
        _update_user(era, user)

    return len(areas), len(users)


def update_stats(last_run, **options):
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
            area_count, user_count = update_era(era, encounters)
        elif options["verbosity"] >= 2:
            print("Skipped era %s" % era)
    return era_count, area_count, user_count, encounter_count
