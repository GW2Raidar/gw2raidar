from django.db import models
from django.db.models.signals import post_save, post_delete
from django.db.models import Q
from django.contrib.auth.models import User
from django.core.validators import RegexValidator
from datetime import datetime, timedelta
import pytz
from fuzzycount import FuzzyCountManager
from hashlib import md5
from analyser.analyser import Profession, Archetype, Elite
from json import loads as json_loads, dumps as json_dumps
from gw2raidar import settings
from os.path import join as path_join
from functools import lru_cache
from time import time
from taggit.managers import TaggableManager
import random
import os
import re


# unique to 30-60s precision
START_RESOLUTION = 60



# XXX TODO Move to a separate module, does not really belong here
# gdrive_service = None
# if hasattr(settings, 'GOOGLE_CREDENTIAL_FILE'):
#     try:
#         from oauth2client.service_account import ServiceAccountCredentials
#         from httplib2 import Http
#         from apiclient import discovery
#         from googleapiclient.http import MediaFileUpload

#         scopes = ['https://www.googleapis.com/auth/drive.file']
#         credentials = ServiceAccountCredentials.from_json_keyfile_name(
#                 settings.GOOGLE_CREDENTIAL_FILE, scopes=scopes)
#         http_auth = credentials.authorize(Http())
#         gdrive_service = discovery.build('drive', 'v3', http=http_auth)
#     except ImportError:
#         # No Google Drive support
#         pass



User._meta.get_field('email')._unique = True



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
    portrait_url = models.URLField(null=True, blank=True) # XXX not using... delete?
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="user_profile")
    last_notified_at = models.IntegerField(db_index=True, default=0, editable=False)
    privacy = models.PositiveSmallIntegerField(editable=False, choices=PRIVACY_CHOICES, default=SQUAD)

    def __str__(self):
        return self.user.username

def _create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)

post_save.connect(_create_user_profile, sender=User)


class Area(models.Model):
    id = models.IntegerField(primary_key=True)
    name = models.CharField(max_length=64, unique=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ('name',)


class Account(models.Model):
    ACCOUNT_NAME_RE = re.compile(r'\S+\.\d{4}') # TODO make more restrictive?
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
    started_at = models.IntegerField(db_index=True)
    name = models.CharField(max_length=255)
    description = models.TextField()

    def __str__(self):
        return "%s (#%d)" % (self.name or "<unnamed>", self.id)

    @staticmethod
    def by_time(started_at):
        return Era.objects.filter(started_at__lte=started_at).latest('started_at')

    class Meta:
        ordering = ('-started_at',)


class Category(models.Model):
    name = models.CharField(max_length=255)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = "categories"


class Upload(ValueModel):
    filename = models.CharField(max_length=255)
    uploaded_at = models.IntegerField(db_index=True)
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='unprocessed_uploads')

    def __str__(self):
        return '%s (%s)' % (self.filename, self.uploaded_by.username)

    def diskname(self):
        if hasattr(settings, 'UPLOAD_DIR'):
            upload_dir = settings.UPLOAD_DIR
        else:
            upload_dir = 'uploads'
        ext = '.' + '.'.join(self.filename.split('.')[1:])
        return path_join(upload_dir, str(self.id) + ext)

    class Meta:
        unique_together = ('filename', 'uploaded_by')

def _delete_upload_file(sender, instance, using, **kwargs):
    try:
        os.remove(instance.diskname())
    except FileNotFoundError:
        pass

post_delete.connect(_delete_upload_file, sender=Upload)


class Notification(ValueModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    created_at = models.IntegerField(db_index=True, default=time)


class Variable(ValueModel):
    key = models.CharField(max_length=255, primary_key=True)

    def __str__(self):
        return '%s=%s' % (self.key, self.val)

    def get(name):
        return Variable.objects.get(key=name).val

    def set(name, value):
        Variable.objects.update_or_create(key=name, defaults={'val': value})


@lru_cache(maxsize=1)
def _dictionary():
    location = os.path.realpath(os.path.join(os.getcwd(), os.path.dirname(__file__)))
    with open(os.path.join(location, "words.txt")) as f:
        return [l.strip() for l in f.readlines()]

def _generate_url_id(size=5):
    return ''.join(w.capitalize() for w in random.sample(_dictionary(), size))

class Encounter(ValueModel):
    url_id = models.TextField(max_length=255, editable=False, unique=True, default=_generate_url_id, verbose_name="URL ID")
    started_at = models.IntegerField(db_index=True)
    duration = models.FloatField()
    success = models.BooleanField()
    filename = models.CharField(max_length=255)
    uploaded_at = models.IntegerField(db_index=True)
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='uploaded_encounters')
    area = models.ForeignKey(Area, on_delete=models.PROTECT, related_name='encounters')
    era = models.ForeignKey(Era, on_delete=models.PROTECT, related_name='encounters')
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, related_name='encounters', null=True, blank=True)
    accounts = models.ManyToManyField(Account, through='Participation', related_name='encounters')
    # hack to try to ensure uniqueness
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
        return '%s (%s, %s, #%s)' % (self.area.name, self.filename, self.uploaded_by.username, self.id)

    # Returns timestamp of closest non-future raid reset (Monday 08:30 UTC)
    @staticmethod
    def week_for(started_at):
        encounter_dt = datetime.utcfromtimestamp(started_at).replace(tzinfo=pytz.UTC)
        reset_dt = (encounter_dt - timedelta(days=encounter_dt.weekday())).replace(hour=7, minute=30, second=0, microsecond=0)
        if reset_dt > encounter_dt:
            reset_dt -= timedelta(weeks=1)
        return int(reset_dt.timestamp())

    def week(self):
        return Encounter.week_for(self.started_at)

    def save(self, *args, **kwargs):
        self.started_at_full, self.started_at_half = Encounter.calculate_start_guards(self.started_at)
        super(Encounter, self).save(*args, **kwargs)

    def diskname(self):
        if hasattr(settings, 'UPLOAD_DIR'):
            upload_dir = settings.UPLOAD_DIR
        else:
            upload_dir = 'uploads'
        return path_join(upload_dir, 'encounters', self.uploaded_by.username, self.filename)

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
        return (started_at_full, started_at_half)


    class Meta:
        index_together = ('area', 'started_at')
        ordering = ('started_at',)
        unique_together = (
            ('area', 'account_hash', 'started_at_full'),
            ('area', 'account_hash', 'started_at_half'),
        )

def _delete_encounter_file(sender, instance, using, **kwargs):
    # if gdrive_service and instance.gdrive_id:
    #     gdrive_service.files().delete(
    #             fileId=instance.gdrive_id).execute()
    try:
        os.remove(instance.diskname())
    except FileNotFoundError:
        pass

post_delete.connect(_delete_encounter_file, sender=Encounter)


class Participation(models.Model):
    PROFESSION_CHOICES = (
            (int(Profession.GUARDIAN), 'Guardian'),
            (int(Profession.WARRIOR), 'Warrior'),
            (int(Profession.ENGINEER), 'Engineer'),
            (int(Profession.RANGER), 'Ranger'),
            (int(Profession.THIEF), 'Thief'),
            (int(Profession.ELEMENTALIST), 'Elementalist'),
            (int(Profession.MESMER), 'Mesmer'),
            (int(Profession.NECROMANCER), 'Necromancer'),
            (int(Profession.REVENANT), 'Revenant'),
        )

    ARCHETYPE_CHOICES = (
            (int(Archetype.POWER), "Power"),
            (int(Archetype.CONDI), "Condi"),
            (int(Archetype.TANK), "Tank"),
            (int(Archetype.HEAL), "Heal"),
            (int(Archetype.SUPPORT), "Support"),
        )

    ELITE_CHOICES = (
            (int(Elite.CORE), "Core"),
            (int(Elite.HEART_OF_THORNS), "Heart of Thorns"),
            (int(Elite.PATH_OF_FIRE), "Path of Fire"),
        )

    encounter = models.ForeignKey(Encounter, on_delete=models.CASCADE, related_name='participations')
    character = models.CharField(max_length=64, db_index=True)
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='participations')
    profession = models.PositiveSmallIntegerField(choices=PROFESSION_CHOICES, db_index=True)
    archetype = models.PositiveSmallIntegerField(choices=ARCHETYPE_CHOICES, db_index=True)
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
                'uploaded_at': self.encounter.uploaded_at,
                'success': self.encounter.success,
                'category': self.encounter.category_id,
                #'tags': list(self.encounter.tags.names()),
                'tags': [t.tag.name for t in self.encounter.tagged_items.all()],
            }

    class Meta:
        unique_together = ('encounter', 'account')


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
