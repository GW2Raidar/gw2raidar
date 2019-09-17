import base64
import os
import re
import copy
import random
from math import floor
from time import time
from hashlib import md5
from functools import lru_cache
from datetime import datetime, timedelta, timezone
from json import loads as json_loads, dumps as json_dumps

import numpy
import pytz
from django.db import models
from django.contrib.auth.models import User
from django.core.validators import RegexValidator
from django.db.models import UniqueConstraint as Unique, Sum, Avg
from django.db.models.signals import post_save, post_delete
from fuzzycount import FuzzyCountManager
from taggit.managers import TaggableManager
from gw2raidar import settings
from analyser.analyser import Profession, Archetype, Elite, BOSSES

# unique to 30-60s precision
START_RESOLUTION = 60

PROFESSION_CHOICES = (
    (-1, "All"),
    (Profession.GUARDIAN, "Guardian"),
    (Profession.WARRIOR, "Warrior"),
    (Profession.ENGINEER, "Engineer"),
    (Profession.RANGER, "Ranger"),
    (Profession.THIEF, "Thief"),
    (Profession.ELEMENTALIST, "Elementalist"),
    (Profession.MESMER, "Mesmer"),
    (Profession.NECROMANCER, "Necromancer"),
    (Profession.REVENANT, "Revenant"),
)

ARCHETYPE_CHOICES = (
    (Archetype.POWER, "Power"),
    (Archetype.CONDI, "Condi"),
    (Archetype.TANK, "Tank"),
    (Archetype.HEAL, "Heal"),
    (Archetype.SUPPORT, "Support"),
)

ELITE_CHOICES = (
    (-1, "All"),
    (Elite.CORE, "Core"),
    (Elite.HEART_OF_THORNS, "Heart of Thorns"),
    (Elite.PATH_OF_FIRE, "Path of Fire"),
)

AVG_STATS = ["crit", "flanking", "scholar", "seaweed"]
SUM_STATS = ["dps", "dps_boss", "dps_received", "total_shielded", "total_received"]
GENERAL_STATS = AVG_STATS + SUM_STATS


def _safe_get(func, default=None):
    try:
        return func()
    except (KeyError, TypeError):
        return default


def _safe_abs(value):
    try:
        return abs(value)
    except TypeError:
        return value


def _safe_get_percent(key, data, fallback=0):
    return data[key] / 100.0 if key in data else fallback


@lru_cache(maxsize=1)
def _dictionary():
    location = os.path.realpath(os.path.join(os.getcwd(), os.path.dirname(__file__)))
    with open(os.path.join(location, "words.txt")) as file:
        return [line.strip() for line in file.readlines()]


def _generate_url_id(size=5):
    return ''.join(w.capitalize() for w in random.sample(_dictionary(), size))


# gdrive_service = None
# if hasattr(settings, 'GOOGLE_CREDENTIAL_FILE'):
#     try:
#         from oauth2client.service_account import ServiceAccountCredentials
#         from httplib2 import Http
#         from apiclient import discovery
#         from googleapiclient.http import MediaFileUpload
#
#         scopes = ['https://www.googleapis.com/auth/drive.file']
#         credentials = ServiceAccountCredentials.from_json_keyfile_name(
#                 settings.GOOGLE_CREDENTIAL_FILE, scopes=scopes)
#         http_auth = credentials.authorize(Http())
#         gdrive_service = discovery.build('drive', 'v3', http=http_auth)
#     except ImportError:
#         # No Google Drive support
#         pass


class ValueModel(models.Model):
    value = models.TextField(default="{}", editable=False)

    @property
    def val(self):
        return json_loads(self.value)

    @val.setter
    def val(self, value):
        self.value = json_dumps(value)

    class Meta:
        abstract = True


class UserProfile(models.Model):
    PRIVATE = 1
    SQUAD = 2
    PUBLIC = 3

    PRIVACY_CHOICES = (
        (PRIVATE, 'Private'),
        (SQUAD, 'Squad'),
        (PUBLIC, 'Public')
    )
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="user_profile")
    last_notified_at = models.IntegerField(db_index=True, default=0, editable=False)
    privacy = models.PositiveSmallIntegerField(editable=False, choices=PRIVACY_CHOICES, default=SQUAD)

    def __str__(self):
        return self.user.username


class Area(models.Model):
    id = models.IntegerField(primary_key=True)
    name = models.CharField(max_length=64, unique=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ('name',)


class Account(models.Model):
    # TODO: Make more restrictive?
    ACCOUNT_NAME_RE = re.compile(r'\S+\.\d{4}')
    API_KEY_RE = re.compile(
        r'-'.join(r'[0-9A-F]{%d}' % n for n in (8, 4, 4, 4, 20, 4, 4, 4, 12)) + r'$',
        re.IGNORECASE)

    user = models.ForeignKey(User, blank=True, null=True, on_delete=models.SET_NULL, related_name='accounts')
    name = models.CharField(max_length=64, unique=True, validators=[RegexValidator(ACCOUNT_NAME_RE)])
    api_key = models.CharField('API key', max_length=72, blank=True, validators=[RegexValidator(API_KEY_RE)])

    def __str__(self):
        return self.name

    class Meta:
        ordering = ('name',)


class Era(ValueModel):
    class Meta:
        ordering = ("-started_at",)
    started_at = models.IntegerField(db_index=True)
    name = models.CharField(max_length=255)
    description = models.TextField()

    def __str__(self):
        return "%s (#%d)" % (self.name or "<unnamed>", self.id)

    def get_area_stats(self, area):
        area_stats = {"group": {"buffs": {}, "buffs_out": {}}, "build": {}, "individual": {}}
        # Squad stats
        for squad_stat in self.squadstat_set.filter(area=area):
            name = None
            if squad_stat.name in GENERAL_STATS:
                target = area_stats["group"]
            elif not squad_stat.out:
                target = area_stats["group"]["buffs"]
            else:
                target = area_stats["group"]["buffs_out"]
                name = squad_stat.name
            target.update(squad_stat.data(name=name))

        # Build stats
        for build_stat in self.buildstat_set.filter(area=area):
            arch = build_stat.archetype
            prof = build_stat.prof
            elite = build_stat.elite
            if arch not in area_stats["build"]:
                area_stats["build"][arch] = {}
            if prof not in area_stats["build"][arch]:
                area_stats["build"][arch][prof] = {}
            if elite not in area_stats["build"][arch][prof]:
                area_stats["build"][arch][prof][elite] = {"buffs": {}, "buffs_out": {}}
            name = None
            if build_stat.name in GENERAL_STATS:
                build_target = area_stats["build"][arch][prof][elite]
                ind_target = area_stats["individual"]
            elif not build_stat.out:
                build_target = area_stats["build"][arch][prof][elite]["buffs"]
                ind_target = area_stats["individual"]["buffs"]
            else:
                build_target = area_stats["build"][arch][prof][elite]["buffs_out"]
                ind_target = area_stats["individual"]["buffs_out"]
                name = build_stat.name
            build_target.update(build_stat.data(name=name))

            # Individual stats
            for key, val in build_stat.data(name=name, avg_val=False, perc_data=False).items():
                if key not in ind_target:
                    ind_target[key] = val
                else:
                    if key.startswith("max"):
                        ind_target[key] = max(ind_target[key], val)
                    elif key.startswith("min"):
                        ind_target[key] = min(ind_target[key], val)
                    else:
                        raise ValueError("Unexpected property " + key + " encountered.")

        return area_stats

    @staticmethod
    def by_time(started_at):
        return Era.objects.filter(started_at__lte=started_at).latest("started_at")


class Category(models.Model):
    name = models.CharField(max_length=255)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = "categories"


class Upload(ValueModel):
    filename = models.CharField(max_length=255)
    uploaded_at = models.IntegerField(db_index=True)
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='unprocessed_uploads')

    def __str__(self):
        if self.uploaded_by:
            uploader = self.uploaded_by.username
        else:
            uploader = 'Unknown'
        return '%s (%s)' % (self.filename, uploader)

    def diskname(self):
        if hasattr(settings, 'UPLOAD_DIR'):
            upload_dir = settings.UPLOAD_DIR
        else:
            upload_dir = 'uploads'
        ext = '.' + '.'.join(self.filename.split('.')[1:])
        return os.path.join(upload_dir, str(self.id) + ext)

    class Meta:
        unique_together = ('filename', 'uploaded_by')


class Notification(ValueModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    created_at = models.IntegerField(db_index=True, default=time)


class Variable(ValueModel):
    key = models.CharField(max_length=255, primary_key=True)

    def __str__(self):
        return '%s=%s' % (self.key, self.val)

    @staticmethod
    def get(name):
        return Variable.objects.get(key=name).val

    @staticmethod
    def set(name, value):
        Variable.objects.update_or_create(key=name, defaults={'val': value})


class EncounterData(models.Model):
    class Meta:
        db_table = "raidar_encounter_data"
    boss = models.TextField()
    cm = models.BooleanField()
    start_timestamp = models.DateTimeField()
    start_tick = models.BigIntegerField()
    end_tick = models.BigIntegerField()
    success = models.BooleanField()
    evtc_version = models.TextField()

    def duration_ticks(self):
        return self.end_tick - self.start_tick

    def duration(self):
        return self.duration_ticks() / 100

    @staticmethod
    def _generate_skill_data(encounter_data, phase, damage_source, damage_target, damage_data):
        for skill_name, skill_data in damage_data["Skill"].items():
            skill = EncounterDamage(encounter_data=encounter_data,
                                    phase=phase,
                                    source=damage_source,
                                    target=damage_target,
                                    skill=skill_name,
                                    damage=skill_data["total"],
                                    crit=_safe_get_percent("crit", skill_data),
                                    fifty=_safe_get_percent("fifty", skill_data),
                                    flanking=_safe_get_percent("flanking", skill_data),
                                    scholar=_safe_get_percent("scholar", skill_data),
                                    seaweed=_safe_get_percent("seaweed", skill_data))
            skill.save()

    @staticmethod
    def from_dump(dump):
        boss = "".join([boss_name for boss_name in dump["Category"]["boss"]["Boss"]])
        data = EncounterData(boss=boss,
                             cm=dump["Category"]["encounter"]["cm"],
                             start_timestamp=datetime.fromtimestamp(dump["Category"]["encounter"]["start"],
                                                                    timezone.utc),
                             start_tick=dump["Category"]["encounter"]["start_tick"],
                             end_tick=dump["Category"]["encounter"]["end_tick"],
                             success=dump["Category"]["encounter"]["success"],
                             evtc_version=dump["Category"]["encounter"]["evtc_version"])
        data.save()

        # Players
        for player_name, player_data in dump["Category"]["status"]["Player"].items():
            account = Account.objects.get_or_create(name=player_data["account"])
            player = EncounterPlayer(encounter_data=data,
                                     account=account[0],
                                     character=player_name,
                                     party=player_data["party"],
                                     profession=player_data["profession"],
                                     elite=player_data["elite"],
                                     archetype=player_data["archetype"],
                                     conc=player_data["concentration"],
                                     condi=player_data["condition"],
                                     heal=player_data["healing"],
                                     tough=player_data["toughness"])
            player.save()

        # Phases
        if "Phase" in dump["Category"]["encounter"]:
            for phase_name, phase_data in dump["Category"]["encounter"]["Phase"].items():
                if phase_name != "All":
                    phase = EncounterPhase(encounter_data=data,
                                           name=phase_name,
                                           start_tick=phase_data["start_tick"])
                    phase.save()
        else:
            phase = EncounterPhase(encounter_data=data,
                                   name="All",
                                   start_tick=dump["Category"]["encounter"]["start_tick"])
            phase.save()

        for phase_name, phase_data in dump["Category"]["combat"]["Phase"].items():
            phase = data.encounterphase_set.filter(name=phase_name).first()
            if phase is None:
                continue

            for player_name, player_data in phase_data["Player"].items():
                player_data = player_data["Metrics"]

                # Buffs
                # Incoming
                if "From" in player_data["buffs"]:
                    for buff_source in player_data["buffs"]["From"]:
                        buff_target = player_name
                        for buff_name, buff_data in player_data["buffs"]["From"][buff_source].items():
                            if buff_data > 0:
                                buff = EncounterBuff(encounter_data=data,
                                                     phase=phase,
                                                     source=buff_source,
                                                     target=buff_target,
                                                     name=buff_name,
                                                     uptime=buff_data if buff_name in ["might", "stability"]
                                                     else buff_data / 100.0)
                                buff.save()
                # Outgoing
                if "To" in player_data["buffs"]:
                    for buff_target in player_data["buffs"]["To"]:
                        buff_source = player_name
                        for buff_name, buff_data in player_data["buffs"]["To"][buff_target].items():
                            if buff_data > 0:
                                buff = EncounterBuff(encounter_data=data,
                                                     phase=phase,
                                                     source=buff_source,
                                                     target=buff_target,
                                                     name=buff_name,
                                                     uptime=buff_data if buff_name in ["might", "stability"]
                                                     else buff_data / 100.0)
                                buff.save()

                # Damage
                # Incoming
                for damage_source, damage_data in player_data["damage"]["From"].items():
                    # Skill breakdown
                    if "Skill" in damage_data:
                        EncounterData._generate_skill_data(data, phase, damage_source, player_name, damage_data)
                # Outgoing
                for damage_target, damage_data in player_data["damage"]["To"].items():
                    # Skill breakdown
                    if damage_target == "*All" and "Skill" in damage_data:
                        EncounterData._generate_skill_data(data, phase, player_name, damage_target, damage_data)
                    # Summary
                    else:
                        # Condi
                        if damage_data["condi"] > 0:
                            condi = EncounterDamage(encounter_data=data,
                                                    phase=phase,
                                                    source=player_name,
                                                    target=damage_target,
                                                    skill="condi",
                                                    damage=damage_data["condi"],
                                                    crit=_safe_get_percent("crit", damage_data),
                                                    fifty=_safe_get_percent("fifty", damage_data),
                                                    flanking=_safe_get_percent("flanking", damage_data),
                                                    scholar=_safe_get_percent("scholar", damage_data),
                                                    seaweed=_safe_get_percent("seaweed", damage_data))
                            condi.save()
                        # Power
                        if damage_data["power"] > 0:
                            power = EncounterDamage(encounter_data=data,
                                                    phase=phase,
                                                    source=player_name,
                                                    target=damage_target,
                                                    skill="power",
                                                    damage=damage_data["power"],
                                                    crit=_safe_get_percent("crit", damage_data),
                                                    fifty=_safe_get_percent("fifty", damage_data),
                                                    flanking=_safe_get_percent("flanking", damage_data),
                                                    scholar=_safe_get_percent("scholar", damage_data),
                                                    seaweed=_safe_get_percent("seaweed", damage_data))
                            power.save()

                # Events
                event_data = player_data["events"]
                event = EncounterEvent(encounter_data=data,
                                       phase=phase,
                                       source=player_name,
                                       disconnect_count=event_data["disconnects"],
                                       disconnect_time=int(event_data["disconnect_time"]),
                                       down_count=event_data["downs"],
                                       down_time=int(event_data["down_time"]),
                                       dead_count=event_data["deaths"],
                                       dead_time=int(event_data["dead_time"]))
                event.save()

                # Shielded
                shield_data = player_data["shielded"]["From"]["*All"]
                shield = EncounterDamage(encounter_data=data,
                                         phase=phase,
                                         source="*All",
                                         target=player_name,
                                         skill="shielded",
                                         damage=-shield_data["total"],
                                         crit=_safe_get_percent("crit", shield_data),
                                         fifty=_safe_get_percent("fifty", shield_data),
                                         flanking=_safe_get_percent("flanking", shield_data),
                                         scholar=_safe_get_percent("scholar", shield_data),
                                         seaweed=_safe_get_percent("seaweed", shield_data))
                shield.save()

                # Mechanics
                if "mechanics" in player_data:
                    for mechanic_name, mechanic_data in player_data["mechanics"].items():
                        mechanic = EncounterMechanic(encounter_data=data,
                                                     phase=phase,
                                                     source=player_name,
                                                     name=mechanic_name,
                                                     count=mechanic_data)
                        mechanic.save()

        # TODO: Remove when fixed
        # If no mechanics were found within phases, they're probably only annotated in the "All" phase
        if not data.encountermechanic_set:
            for player_name, player_data in dump["Category"]["combat"]["Phase"]["All"]["Player"].items():
                if "mechanics" in player_data:
                    for mechanic_name, mechanic_data in player_data["mechanics"].items():
                        mechanic = EncounterMechanic(encounter_data=data,
                                                     phase="All",
                                                     source=player_name,
                                                     name=mechanic_name,
                                                     count=mechanic_data)
                        mechanic.save()
        return data


class Encounter(models.Model):
    encounter_data = models.ForeignKey(EncounterData, db_column="encounter_data_id", on_delete=models.CASCADE)
    url_id = models.TextField(max_length=255, editable=False, unique=True, default=_generate_url_id,
                              verbose_name="URL ID")
    started_at = models.IntegerField(db_index=True)
    duration = models.FloatField()
    success = models.BooleanField()
    filename = models.CharField(max_length=255)
    uploaded_on = models.DateTimeField()
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='uploaded_encounters')
    area = models.ForeignKey(Area, on_delete=models.PROTECT, related_name='encounters')
    era = models.ForeignKey(Era, on_delete=models.PROTECT, related_name='encounters')
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, related_name='encounters', null=True, blank=True)
    accounts = models.ManyToManyField(Account, through='Participation', related_name='encounters')
    # Hack to try to ensure uniqueness
    account_hash = models.CharField(max_length=32, editable=False)
    started_at_full = models.IntegerField(editable=False)
    started_at_half = models.IntegerField(editable=False)
    # Google Drive
    gdrive_id = models.CharField(max_length=255, editable=False, null=True, blank=True)
    gdrive_url = models.CharField(max_length=255, editable=False, null=True, blank=True)
    tags = TaggableManager(blank=True)
    has_evtc = models.BooleanField(default=True, editable=False)

    objects = FuzzyCountManager()

    def __str__(self):
        if self.uploaded_by:
            uploader = self.uploaded_by.username
        else:
            uploader = 'Unknown'
        return '%s (%s, %s, #%s)' % (self.area.name, self.filename, uploader, self.id)

    @staticmethod
    def week_for(started_at):
        """Returns timestamp of closest non-future raid reset (Monday 08:30 UTC)"""
        encounter_dt = datetime.utcfromtimestamp(started_at).replace(tzinfo=pytz.UTC)
        reset_dt = (encounter_dt - timedelta(days=encounter_dt.weekday())).replace(hour=7, minute=30, second=0,
                                                                                   microsecond=0)
        if reset_dt > encounter_dt:
            reset_dt -= timedelta(weeks=1)
        return int(reset_dt.timestamp())

    def calc_phase_duration(self, phase):
        if phase == "All":
            return self.duration
        start_tick = phase.start_tick
        next_phase = self.encounter_data.encounterphase_set.filter(start_tick__gt=start_tick).order_by(
            "start_tick").first()
        end_tick = self.encounter_data.end_tick if next_phase is None else next_phase.start_tick
        return (end_tick - start_tick) / 1000.0

    def json_dump(self, privacy_parties=None, participated=False):
        data = self.encounter_data
        phases = data.encounterphase_set.order_by("start_tick")
        players = data.encounterplayer_set.filter(account_id__isnull=False)
        parties = privacy_parties if privacy_parties else\
            {party_name: [player.data() for player in players.filter(party=party_name)]
             for party_name in players.values_list("party", flat=True).distinct()}

        try:
            area_stats = EraAreaStore.objects.get(era=self.era, area=self.area).val
        except EraAreaStore.DoesNotExist:
            area_stats = None

        # Generate phase data
        phase_data = {phase.name: {
            "parties": {party_name: EncounterPhase.breakdown(self, party_data, phase, group=True) for
                        party_name, party_data in parties.items()}} for phase in phases}

        # Add phase meta data
        for phase in phases:
            phase_data[phase.name]["duration"] = self.calc_phase_duration(phase)
            phase_data[phase.name]["group"] = area_stats[phase.name]["group"] if area_stats else {}
            phase_data[phase.name]["individual"] = area_stats[phase.name]["individual"] if area_stats else {}

            # Add player data
            for party_name, party in phase_data[phase.name]["parties"].items():
                for member in party["members"]:
                    member.update(EncounterPhase.breakdown(self, member, phase))

        # Generate "All" phase from existing data
        if "All" not in phase_data:
            phase_data["All"] = {
                "duration": self.calc_phase_duration("All"),
                "group": _safe_get(lambda: area_stats["All"]["group"]),
                "individual": _safe_get(lambda: area_stats["All"]["individual"]),
                "parties": {party_name: EncounterPhase.all_breakdown(phase_data, self, party_name, party_data) for
                            party_name, party_data in parties.items()},
            }

        # Generate total squad stats from existing data
        for phase_name, squad_phase in phase_data.items():
            squad_phase.update({
                "actual": {"dps": 0},
                "actual_boss": {"dps": 0},
                "received": {"total": 0},
                "shielded": {"total": 0},
                "buffs": {},
                "buffs_out": {},
                "mechanics": {},
                "events": {},
            })
            squad_size = 0

            for party_name, party_data in parties.items():
                party_phase = squad_phase["parties"][party_name]
                party_size = len(party_data)

                # Damage-like stats
                for target in ["actual", "actual_boss", "received", "shielded"]:
                    for key, val in party_phase[target].items():
                        if key != "Skill":
                            if key not in squad_phase[target]:
                                squad_phase[target][key] = 0
                            if key in ["total", "power", "condi", "dps", "power_dps", "condi_dps"]:
                                squad_phase[target][key] += val
                            else:
                                squad_phase[target][key] =\
                                    squad_phase[target][key] * squad_size / (squad_size + party_size)\
                                    + val * party_size / (squad_size + party_size)

                # Buffs
                for buff, uptime in party_phase["buffs"].items():
                    if buff not in squad_phase["buffs"]:
                        squad_phase["buffs"][buff] = 0
                    squad_phase["buffs"][buff] = squad_phase["buffs"][buff] * squad_size / (squad_size + party_size)\
                        + uptime * party_size / (squad_size + party_size)

                # Additive stats
                for target in ["buffs_out", "events", "mechanics"]:
                    for key, val in party_phase[target].items():
                        if key not in squad_phase[target]:
                            squad_phase[target][key] = 0
                        squad_phase[target][key] += val

                squad_size += party_size

        # Add performance data to members
        for phase_name, prv_phase_data in phase_data.items():
            for party_data in prv_phase_data["parties"].values():
                for member in party_data["members"]:
                    arch = str(member["archetype"])
                    prof = str(member["profession"])
                    elite = str(member["elite"])
                    member["performance"] = _safe_get(lambda a=arch, p=prof, e=elite:
                                                      area_stats[phase_name]["build"][a][p][e])

        max_player_dps = max([member["actual"]["dps"] for phase in phase_data.values()
                              for party in phase["parties"].values()
                              for member in party["members"]])
        max_player_recv = max([member["received"]["total"] for phase in phase_data.values()
                               for party in phase["parties"].values()
                               for member in party["members"]])

        data = {
            "encounter": {
                "evtc_version": data.evtc_version,
                "id": self.id,
                "url_id": self.url_id,
                "name": self.area.name,
                "filename": self.filename,
                "uploaded_at": self.uploaded_on.timestamp(),
                "uploaded_by": self.uploaded_by.username,
                "started_at": self.started_at,
                "duration": self.duration,
                "success": self.success,
                "tags": self.tagstring,
                "category": self.category_id,
                "phase_order": [phase.name for phase in phases],
                "participated": participated,
                "boss_metrics": [metric.__dict__ for metric in BOSSES[self.area_id].metrics],
                "max_player_dps": max_player_dps,
                "max_player_recv": max_player_recv,
                "phases": phase_data,
            }
        }
        if "All" not in data["encounter"]["phase_order"]:
            data["encounter"]["phase_order"].append("All")
        return data

    def week(self):
        return Encounter.week_for(self.started_at)

    def save(self, force_insert=False, force_update=False, using=None, update_fields=None):
        self.started_at_full, self.started_at_half = Encounter.calculate_start_guards(self.started_at)
        super(Encounter, self).save(force_insert, force_update, using, update_fields)

    def diskname(self):
        if not self.uploaded_by:
            return None
        if hasattr(settings, 'UPLOAD_DIR'):
            upload_dir = settings.UPLOAD_DIR
        else:
            upload_dir = 'uploads'
        return os.path.join(upload_dir, 'encounters', self.uploaded_by.username, self.filename)

    def update_has_evtc(self):
        self.has_evtc = os.path.isfile(self.diskname())
        self.save()

    @property
    def tagstring(self):
        return ','.join(self.tags.names())

    @tagstring.setter
    def tagstring(self, value):
        self.tags.set(*value.split(','))

    @staticmethod
    def calculate_account_hash(account_names):
        conc = ':'.join(sorted(account_names))
        hash_object = md5(conc.encode())
        return hash_object.hexdigest()

    @staticmethod
    def calculate_start_guards(started_at):
        started_at_full = round(started_at / START_RESOLUTION) * START_RESOLUTION
        started_at_half = round((started_at + START_RESOLUTION / 2) / START_RESOLUTION) * START_RESOLUTION
        return started_at_full, started_at_half

    class Meta:
        index_together = ('area', 'started_at')
        ordering = ('started_at',)
        unique_together = (
            ('area', 'account_hash', 'started_at_full'),
            ('area', 'account_hash', 'started_at_half'),
        )


class Participation(models.Model):
    encounter = models.ForeignKey(Encounter, on_delete=models.CASCADE, related_name='participations')
    character = models.CharField(max_length=64, db_index=True)
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='participations')
    archetype = models.PositiveSmallIntegerField(choices=ARCHETYPE_CHOICES, db_index=True)
    profession = models.PositiveSmallIntegerField(choices=PROFESSION_CHOICES, db_index=True)
    elite = models.PositiveSmallIntegerField(choices=ELITE_CHOICES, db_index=True)
    party = models.PositiveSmallIntegerField(db_index=True)

    def __str__(self):
        return '%s (%s) in %s' % (self.character, self.account.name, self.encounter)

    def data(self):
        return {
            'id': self.encounter.id,
            'url_id': self.encounter.url_id,
            'area': self.encounter.area.name,
            'started_at': self.encounter.started_at,
            'duration': self.encounter.duration,
            'character': self.character,
            'account': self.account.name,
            'profession': self.profession,
            'archetype': self.archetype,
            'elite': self.elite,
            'uploaded_at': self.encounter.uploaded_on.timestamp(),
            'success': self.encounter.success,
            'category': self.encounter.category_id,
            'tags': [t.tag.name for t in self.encounter.tagged_items.all()],
        }

    class Meta:
        unique_together = ('encounter', 'account')


class AbstractStat(models.Model):
    class Meta:
        abstract = True
        constraints = [Unique(fields=["era", "area", "phase", "name", "out"], name="stats_group_unique")]

    era = models.ForeignKey(Era, on_delete=models.CASCADE)
    area = models.ForeignKey(Area, on_delete=models.CASCADE)
    phase = models.TextField()
    name = models.TextField()
    out = models.BooleanField()
    min_val = models.FloatField(editable=False)
    max_val = models.FloatField(editable=False)
    avg_val = models.FloatField(editable=False)
    perc_data = models.TextField(default="", editable=False)

    # Internal storage
    raw_data = []
    percentiles = None

    def add_data_point(self, data_point):
        self.raw_data.append(data_point)

    def get_percentile(self, percentile):
        if self.perc_data:
            if not self.percentiles:
                self.percentiles = numpy.frombuffer(base64.b64decode(self.perc_data.encode("utf-8")),
                                                    dtype=numpy.float32)
            # Clamp percentile to range 0-100
            percentile = max(0, min(percentile, len(self.percentiles)))
            return self.percentiles[percentile] if percentile < len(self.percentiles) else self.max_val
        return None

    def data(self, name=None, min_val=True, max_val=True, avg_val=True, perc_data=True):
        name = name if name else self.name + ("_out" if self.out else "")
        data = {}
        if min_val:
            data["min_" + name] = self.min_val
        if max_val:
            data["max_" + name] = self.max_val
        if avg_val:
            data["avg_" + name] = self.avg_val
        if perc_data and self.perc_data:
            data["perc_" + name] = self.perc_data
        return data

    def save(self, *args, **kwargs):
        if self.raw_data:
            self.raw_data.sort()
            length = len(self.raw_data)
            percent_length = length / 100
            self.min_val = self.raw_data[0]
            self.max_val = self.raw_data[-1]
            self.avg_val = sum(self.raw_data) / length
            self.perc_data = base64.b64encode(numpy.array([self.raw_data[floor(i * percent_length)]
                                                           for i in range(0, 100)],
                                                          dtype=numpy.float32).tobytes()).decode("utf-8")
        super(AbstractStat, self).save(*args, **kwargs)


class SquadStat(AbstractStat):
    class Meta:
        db_table = "raidar_stats_squad"


class BuildStat(AbstractStat):
    class Meta:
        db_table = "raidar_stats_build"
        constraints = [Unique(fields=["era", "area", "phase", "archetype", "prof", "elite", "name", "out"],
                              name="stats_group_unique")]
    archetype = models.PositiveSmallIntegerField(choices=ARCHETYPE_CHOICES, db_index=True)
    prof = models.PositiveSmallIntegerField(choices=PROFESSION_CHOICES, db_index=True)
    elite = models.PositiveSmallIntegerField(choices=ELITE_CHOICES, db_index=True)


class UserStat(AbstractStat):
    class Meta:
        db_table = "raidar_stats_user"
        constraints = [Unique(fields=["era", "area", "phase", "user", "archetype", "prof", "elite", "name", "out"],
                              name="stats_group_unique")]
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    archetype = models.PositiveSmallIntegerField(choices=ARCHETYPE_CHOICES, db_index=True)
    prof = models.PositiveSmallIntegerField(choices=PROFESSION_CHOICES, db_index=True)
    elite = models.PositiveSmallIntegerField(choices=ELITE_CHOICES, db_index=True)


class EraAreaStore(ValueModel):
    era = models.ForeignKey(Era, on_delete=models.CASCADE, related_name="era_area_stores")
    area = models.ForeignKey(Area, on_delete=models.CASCADE, related_name="era_area_stores")
    leaderboards_value = models.TextField(default="{}", editable=False)

    @property
    def leaderboards(self):
        return json_loads(self.leaderboards_value)

    @leaderboards.setter
    def leaderboards(self, value):
        self.leaderboards_value = json_dumps(value)


class EraUserStore(ValueModel):
    era = models.ForeignKey(Era, on_delete=models.CASCADE, related_name="era_user_stores")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="era_user_stores")


class RestatPerfStats(models.Model):
    started_on = models.DateTimeField()
    ended_on = models.DateTimeField()
    number_users = models.IntegerField()
    number_eras = models.IntegerField()
    number_areas = models.IntegerField()
    number_new_encounters = models.IntegerField()
    number_pruned_evtcs = models.IntegerField()
    was_force = models.BooleanField()


class EncounterAttribute(models.Model):
    class Meta:
        abstract = True
    encounter_data = models.ForeignKey(EncounterData, db_column="encounter_data_id", on_delete=models.CASCADE)


class EncounterPhase(EncounterAttribute):
    class Meta:
        db_table = "raidar_encounter_phase"
        constraints = [Unique(fields=["encounter_data", "name"], name="enc_phase_unique")]
    name = models.TextField()
    start_tick = models.BigIntegerField()

    # TODO: Fix numbers
    @staticmethod
    def breakdown(prv_encounter, players, phase, group=False):
        prv_players = [player["name"] for player in players] if group else [players["name"]]
        phase_duration = prv_encounter.calc_phase_duration(phase)
        buffs = prv_encounter.encounter_data.encounterbuff_set.filter(phase=phase)
        events = prv_encounter.encounter_data.encounterevent_set.filter(phase=phase)
        damage = prv_encounter.encounter_data.encounterdamage_set.filter(phase=phase)
        mechanics = prv_encounter.encounter_data.encountermechanic_set.filter(phase=phase)

        prv_phase_data = {
            "actual": EncounterDamage.breakdown(damage.filter(source__in=prv_players,
                                                              target="*All",
                                                              damage__gt=0),
                                                phase_duration, group=group),
            "actual_boss": EncounterDamage.breakdown(damage.filter(source__in=prv_players,
                                                                   target="*Boss",
                                                                   damage__gt=0),
                                                     phase_duration, group=group),
            "received": EncounterDamage.breakdown(damage.filter(target__in=prv_players,
                                                                damage__gt=0),
                                                  phase_duration, group=group),
            "shielded": EncounterDamage.breakdown(damage.filter(target__in=prv_players,
                                                                damage__lt=0),
                                                  phase_duration, group=group, absolute=True),
            "buffs": EncounterBuff.breakdown(buffs.filter(target__in=prv_players)),
            "buffs_out": EncounterBuff.breakdown(buffs.filter(source__in=prv_players), use_sum=True),
            "events": EncounterEvent.summarize(events.filter(source__in=prv_players)),
            "mechanics": {mechanic["name"]: mechanic["count__sum"] for mechanic in
                          mechanics.filter(source__in=prv_players).values("name").annotate(Sum("count"))},
        }
        if group:
            prv_phase_data["members"] = copy.deepcopy(players)

        return prv_phase_data

    @staticmethod
    def all_breakdown(phase_dump, prv_encounter, party_name, player_data):
        all_phase = {
            "actual": {},
            "actual_boss": {},
            "received": {},
            "shielded": {},
            "buffs": {},
            "buffs_out": {},
            "events": {},
            "mechanics": {},
            "members": copy.deepcopy(player_data),
        }

        for phase_data in phase_dump.values():
            phase_duration = phase_data["duration"]

            # Damage-like stats
            for target in ["actual", "actual_boss", "received", "shielded"]:
                # Subgroup
                for key, val in phase_data["parties"][party_name][target].items():
                    if key != "Skill":
                        if key not in all_phase[target]:
                            all_phase[target][key] = 0
                        if key in ["total", "power", "condi", "dps", "power_dps", "condi_dps"]:
                            all_phase[target][key] += val
                        else:
                            all_phase[target][key] += val * (phase_duration / prv_encounter.duration)
                # Players
                for member_id, member in enumerate(all_phase["members"]):
                    if target not in member:
                        member[target] = {}
                    for key, val in phase_data["parties"][party_name]["members"][member_id][target].items():
                        # Overall damage stats
                        if key != "Skill":
                            if key not in member[target]:
                                member[target][key] = 0
                            if key in ["total", "power", "condi", "dps", "power_dps", "condi_dps"]:
                                member[target][key] += val
                            else:
                                member[target][key] += val * (phase_duration / prv_encounter.duration)
                        # Skill summaries
                        else:
                            if "Skill" not in member[target]:
                                member[target]["Skill"] = {}
                            for skill_name, skill_data in val.items():
                                if skill_name not in member[target]["Skill"]:
                                    member[target]["Skill"][skill_name] = {"skill": skill_name}
                                for skill_key, skill_val in skill_data.items():
                                    if skill_key != "skill":
                                        if skill_key not in member[target]["Skill"][skill_name]:
                                            member[target]["Skill"][skill_name][skill_key] = 0
                                        if skill_key in ["total", "dps"]:
                                            member[target]["Skill"][skill_name][skill_key] += skill_val
                                        else:
                                            # TODO: This solution for calculating average stats is imprecise!
                                            member[target]["Skill"][skill_name][skill_key] +=\
                                                skill_val * (phase_duration / prv_encounter.duration)

            # Buffs
            for target in ["buffs", "buffs_out"]:
                # Subgroup
                for buff, uptime in phase_data["parties"][party_name][target].items():
                    if buff not in all_phase[target]:
                        all_phase[target][buff] = 0
                    all_phase[target][buff] += uptime * (phase_duration / prv_encounter.duration)
                # Players
                for member_id, member in enumerate(all_phase["members"]):
                    if target not in all_phase["members"][member_id]:
                        member[target] = {}
                    for buff, uptime in phase_data["parties"][party_name]["members"][member_id][target].items():
                        if buff not in member[target]:
                            member[target][buff] = 0
                        member[target][buff] += uptime * (phase_duration / prv_encounter.duration)

            # Additive stats
            for target in ["events", "mechanics"]:
                for key, val in phase_data["parties"][party_name][target].items():
                    if key not in all_phase[target]:
                        all_phase[target][key] = 0
                    all_phase[target][key] += val
                # Players
                for member_id, member in enumerate(all_phase["members"]):
                    if target not in all_phase["members"][member_id]:
                        member[target] = {}
                    for key, val in phase_data["parties"][party_name]["members"][member_id][target].items():
                        if key not in member[target]:
                            member[target][key] = 0
                        member[target][key] += val

        # Update DPS
        for target in ["actual", "actual_boss", "received", "shielded"]:
            all_phase[target]["dps"] = all_phase[target]["total"] / prv_encounter.duration
            all_phase[target]["power_dps"] = all_phase[target]["power"] / prv_encounter.duration
            all_phase[target]["condi_dps"] = all_phase[target]["condi"] / prv_encounter.duration

            for member in all_phase["members"]:
                member[target]["dps"] = member[target]["total"] / prv_encounter.duration
                member[target]["power_dps"] = member[target]["power"] / prv_encounter.duration
                member[target]["condi_dps"] = member[target]["condi"] / prv_encounter.duration

        # TODO: Remove when fixed
        # If no mechanics were found within phases, they're probably only annotated in the "All" phase
        if not all_phase["mechanics"]:
            all_phase["mechanics"] = {
                mechanic["name"]: mechanic["count__sum"] for mechanic in
                prv_encounter.encounter_data.encountermechanic_set
                .filter(source__in=[player["name"] for player in player_data]).values("name").annotate(Sum("count"))
            }

        return all_phase


class SourcedEncounterAttribute(EncounterAttribute):
    class Meta:
        abstract = True
    phase = models.ForeignKey(EncounterPhase, on_delete=models.CASCADE)
    source = models.TextField()


class TargetedEncounterAttribute(SourcedEncounterAttribute):
    class Meta:
        abstract = True
    target = models.TextField()


class NamedSourcedEncounterAttribute(SourcedEncounterAttribute):
    class Meta:
        abstract = True
    name = models.TextField()


class EncounterEvent(SourcedEncounterAttribute):
    class Meta:
        db_table = "raidar_encounter_event"
        constraints = [Unique(fields=["encounter_data", "phase", "source"], name="enc_evt_unique")]
    disconnect_count = models.PositiveIntegerField()
    disconnect_time = models.PositiveIntegerField()
    down_count = models.PositiveIntegerField()
    down_time = models.PositiveIntegerField()
    dead_count = models.PositiveIntegerField()
    dead_time = models.PositiveIntegerField()

    def get_inactive_time(self):
        return self.disconnect_time + self.down_time + self.dead_time

    @staticmethod
    def summarize(query):
        data = {
            "disconnect_count": 0,
            "disconnect_time": 0,
            "down_count": 0,
            "down_time": 0,
            "dead_count": 0,
            "dead_time": 0,
        }

        for row in query:
            for stat in data:
                data[stat] += row.__dict__[stat]
        return data


class EncounterMechanic(NamedSourcedEncounterAttribute):
    class Meta:
        constraints = [Unique(fields=["encounter_data", "phase", "source", "name"], name="enc_mech_unique")]
        db_table = "raidar_encounter_mechanic"
    count = models.PositiveIntegerField()


class EncounterBuff(TargetedEncounterAttribute):
    class Meta:
        db_table = "raidar_encounter_buff"
        constraints = [Unique(fields=["encounter_data", "phase", "source", "target", "name"], name="enc_buff_unique")]
    name = models.TextField()
    uptime = models.FloatField()

    @staticmethod
    def breakdown(buff_data, use_sum=False):
        prv_buff_data = {buff["name"]: buff["sum"] if use_sum else buff["avg"] for buff in
                         buff_data.values("name").annotate(avg=Avg("uptime"), sum=Sum("uptime"))}
        for name, uptime in prv_buff_data.items():
            if name not in ["might", "stability"]:
                prv_buff_data[name] = uptime * 100.0
        return prv_buff_data


class EncounterDamage(TargetedEncounterAttribute):
    class Meta:
        db_table = "raidar_encounter_damage"
        constraints = [Unique(fields=["encounter_data", "phase", "source", "target", "skill"], name="enc_dmg_unique")]
    skill = models.TextField()
    damage = models.IntegerField()
    crit = models.FloatField()
    fifty = models.FloatField()
    flanking = models.FloatField()
    scholar = models.FloatField()
    seaweed = models.FloatField()

    def data(self):
        return {
            "skill": self.skill,
            "total": self.damage,
            "crit": self.crit * 100.0,
            "fifty": self.fifty * 100.0,
            "flanking": self.flanking * 100.0,
            "scholar": self.scholar * 100.0,
            "seaweed": self.seaweed * 100.0,
        }

    # TODO: Fix numbers
    @staticmethod
    def breakdown(dmg_data, phase_duration, group=False, absolute=False):
        prv_dmg_data = {} if group else {
            "Skill": {damage.skill: damage.data() for damage in dmg_data.exclude(skill__in=["power, condi"])}}
        power_data = EncounterDamage.summarize(dmg_data, "power", absolute=absolute)
        for key, val in power_data.items():
            prv_dmg_data["power" if key == "total" else key] = val
        prv_dmg_data["condi"] = EncounterDamage.summarize(dmg_data, "condi", absolute=absolute)["total"]
        prv_dmg_data["total"] = prv_dmg_data["power"] + prv_dmg_data["condi"]
        prv_dmg_data["dps"] = prv_dmg_data["total"] / phase_duration
        prv_dmg_data["condi_dps"] = prv_dmg_data["condi"] / phase_duration
        prv_dmg_data["power_dps"] = prv_dmg_data["power"] / phase_duration
        return prv_dmg_data

    @staticmethod
    def summarize(query, target="all", absolute=False):
        if target != "all":
            query = query.filter(skill=target)
            if len(query) == 0:
                query = query.filter(skill__in=EncounterDamage.conditions()) if target == "condi"\
                    else query.exclude(skill__in=EncounterDamage.conditions())

        data = {"total": [], "crit": [], "fifty": [], "flanking": [], "scholar": [], "seaweed": []}
        for row in query:
            data["total"].append(row.damage)
            data["crit"].append(row.crit)
            data["fifty"].append(row.fifty)
            data["flanking"].append(row.flanking)
            data["scholar"].append(row.scholar)
            data["seaweed"].append(row.seaweed)

        # TODO: This solution for calculating average stats is imprecise!
        data["total"] = sum(data["total"])
        data["crit"] = sum(data["crit"]) / max(len(data["crit"]), 1)
        data["fifty"] = sum(data["fifty"]) / max(len(data["fifty"]), 1)
        data["flanking"] = sum(data["flanking"]) / max(len(data["flanking"]), 1)
        data["scholar"] = sum(data["scholar"]) / max(len(data["scholar"]), 1)
        data["seaweed"] = sum(data["seaweed"]) / max(len(data["seaweed"]), 1)

        if absolute:
            data = {key: _safe_abs(val) for key, val in data.items()}
        return data

    @staticmethod
    def conditions():
        return ["Bleeding", "Burning", "Confusion", "Poisoned", "Torment"]


# TODO: Combine with Participation
class EncounterPlayer(EncounterAttribute):
    class Meta:
        db_table = "raidar_encounter_player"
        constraints = [Unique(fields=["encounter_data", "account"], name="enc_player_unique")]
    account = models.ForeignKey(Account, on_delete=models.CASCADE)
    character = models.TextField()
    party = models.PositiveIntegerField()
    profession = models.PositiveIntegerField()
    elite = models.PositiveIntegerField()
    archetype = models.PositiveIntegerField()
    conc = models.PositiveIntegerField()
    condi = models.PositiveIntegerField()
    heal = models.PositiveIntegerField()
    tough = models.PositiveIntegerField()

    def data(self):
        return {
            "name": self.character,
            "account": self.account.name,
            "profession": self.profession,
            "elite": self.elite,
            "archetype": self.archetype,
            "concentration": self.conc,
            "condition": self.condi,
            "healing": self.heal,
            "toughness": self.tough,
        }


def _create_user_profile(sender, instance, created, **kwargs):  # pylint: disable=unused-argument
    if created:
        UserProfile.objects.create(user=instance)


def _delete_upload_file(sender, instance, using, **kwargs):  # pylint: disable=unused-argument
    filename = instance.diskname()
    if filename:
        try:
            os.remove(filename)
        except FileNotFoundError:
            pass


def _delete_encounter_file(sender, instance, using, **kwargs):  # pylint: disable=unused-argument
    # if gdrive_service and instance.gdrive_id:
    #     gdrive_service.files().delete(
    #             fileId=instance.gdrive_id).execute()
    filename = instance.diskname()
    if filename:
        try:
            os.remove(filename)
        except FileNotFoundError:
            pass


User._meta.get_field('email')._unique = True  # pylint: disable=protected-access
post_save.connect(_create_user_profile, sender=User)
post_delete.connect(_delete_upload_file, sender=Upload)
post_delete.connect(_delete_encounter_file, sender=Encounter)
