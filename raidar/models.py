from django.db import models
from django.db.models.signals import post_save, post_delete
from django.db.models import Q
from django.contrib.auth.models import User
from django.core.validators import RegexValidator
from hashlib import md5
from analyser.analyser import Archetype, Elite
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
gdrive_service = None
if hasattr(settings, 'GOOGLE_CREDENTIAL_FILE'):
    try:
        from oauth2client.service_account import ServiceAccountCredentials
        from httplib2 import Http
        from apiclient import discovery
        from googleapiclient.http import MediaFileUpload

        scopes = ['https://www.googleapis.com/auth/drive.file']
        credentials = ServiceAccountCredentials.from_json_keyfile_name(
                settings.GOOGLE_CREDENTIAL_FILE, scopes=scopes)
        http_auth = credentials.authorize(Http())
        gdrive_service = discovery.build('drive', 'v3', http=http_auth)
    except ImportError:
        # No Google Drive support
        pass



User._meta.get_field('email')._unique = True

class UserProfile(models.Model):
    PRIVATE = 1
    SQUAD = 2
    PUBLIC = 3

    PRIVACY_CHOICES = (
            (PRIVATE, 'Private'),
            (SQUAD, 'Squad'),
            (PUBLIC, 'Public')
        )
    portrait_url = models.URLField(null=True) # XXX not using... delete?
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="user_profile")
    last_notified_at = models.IntegerField(db_index=True, default=0, editable=False)
    privacy = models.PositiveSmallIntegerField(editable=False, choices=PRIVACY_CHOICES, default=PUBLIC)

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


class Character(models.Model):
    GUARDIAN = 1
    WARRIOR = 2
    ENGINEER = 3
    RANGER = 4
    THIEF = 5
    ELEMENTALIST = 6
    MESMER = 7
    NECROMANCER = 8
    REVENANT = 9

    PROFESSION_CHOICES = (
            (GUARDIAN, 'Guardian'),
            (WARRIOR, 'Warrior'),
            (ENGINEER, 'Engineer'),
            (RANGER, 'Ranger'),
            (THIEF, 'Thief'),
            (ELEMENTALIST, 'Elementalist'),
            (MESMER, 'Mesmer'),
            (NECROMANCER, 'Necromancer'),
            (REVENANT, 'Revenant'),
        )

    SPECIALISATIONS = { (id, 0): name for id, name in PROFESSION_CHOICES }
    SPECIALISATIONS.update({
        (GUARDIAN, 1): 'Dragonhunter',
        (WARRIOR, 1): 'Berserker',
        (ENGINEER, 1): 'Scrapper',
        (RANGER, 1): 'Druid',
        (THIEF, 1): 'Daredevil',
        (ELEMENTALIST, 1): 'Tempest',
        (MESMER, 1): 'Chronomancer',
        (NECROMANCER, 1): 'Reaper',
        (REVENANT, 1): 'Herald',

        (GUARDIAN, 2): 'Firebrand',
        (WARRIOR, 2): 'Spellbreaker',
        (ENGINEER, 2): 'Holosmith',
        (RANGER, 2): 'Soulbeast',
        (THIEF, 2): 'Deadeye',
        (ELEMENTALIST, 2): 'Weaver',
        (MESMER, 2): 'Mirage',
        (NECROMANCER, 2): 'Scourge',
        (REVENANT, 2): 'Renegade',
    })

    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='characters')
    name = models.CharField(max_length=64, db_index=True)
    profession = models.PositiveSmallIntegerField(choices=PROFESSION_CHOICES, db_index=True)
    verified_at = models.DateTimeField(auto_now_add=True) # XXX don't remember this... delete?

    def __str__(self):
        return self.name

    class Meta:
        # name is not necessarily unique, just unique at a time
        unique_together = ('name', 'account', 'profession')
        ordering = ('name',)


class Era(models.Model):
    started_at = models.IntegerField(db_index=True)
    name = models.CharField(max_length=255, null=True)
    description = models.TextField(null=True)

    def __str__(self):
        return "%s (#%d)" % (self.name or "<unnamed>", self.id)

    @staticmethod
    def by_time(started_at):
        return Era.objects.filter(started_at__lte=started_at).latest('started_at')


class Category(models.Model):
    name = models.CharField(max_length=255)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = "categories"


class Upload(models.Model):
    filename = models.CharField(max_length=255)
    uploaded_at = models.IntegerField(db_index=True)
    uploaded_by = models.ForeignKey(User, related_name='unprocessed_uploads')

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


class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    value = models.TextField(default="{}")
    created_at = models.IntegerField(db_index=True, default=time)

    @property
    def val(self):
        return json_loads(self.value)

    @val.setter
    def val(self, value):
        self.value = json_dumps(value)


class Variable(models.Model):
    key = models.CharField(max_length=255, primary_key=True)
    value = models.TextField(null=True)

    def __str__(self):
        return '%s=%s' % (self.key, self.val)

    @property
    def val(self):
        return json_loads(self.value)

    @val.setter
    def val(self, value):
        self.value = json_dumps(value)

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

class Encounter(models.Model):
    url_id = models.TextField(max_length=255, editable=False, unique=True, default=_generate_url_id, verbose_name="URL ID")
    started_at = models.IntegerField(db_index=True)
    duration = models.FloatField()
    success = models.BooleanField()
    filename = models.CharField(max_length=255)
    uploaded_at = models.IntegerField(db_index=True)
    uploaded_by = models.ForeignKey(User, related_name='uploaded_encounters')
    area = models.ForeignKey(Area, on_delete=models.PROTECT, related_name='encounters')
    era = models.ForeignKey(Era, on_delete=models.PROTECT, related_name='encounters')
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, related_name='encounters', null=True)
    characters = models.ManyToManyField(Character, through='Participation', related_name='encounters')
    dump = models.TextField(editable=False)
    # hack to try to ensure uniqueness
    account_hash = models.CharField(max_length=32, editable=False)
    started_at_full = models.IntegerField(editable=False)
    started_at_half = models.IntegerField(editable=False)
    # Google Drive
    gdrive_id = models.CharField(max_length=255, editable=False, null=True)
    gdrive_url = models.CharField(max_length=255, editable=False, null=True)
    tags = TaggableManager(blank=True)

    def __str__(self):
        return '%s (%s, %s, #%s)' % (self.area.name, self.filename, self.uploaded_by.username, self.id)

    def save(self, *args, **kwargs):
        self.started_at_full, self.started_at_half = Encounter.calculate_start_guards(self.started_at)
        super(Encounter, self).save(*args, **kwargs)

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

def _delete_gdrive_file(sender, instance, using, **kwargs):
    if gdrive_service and instance.gdrive_id:
        gdrive_service.files().delete(
                fileId=instance.gdrive_id).execute()

post_delete.connect(_delete_gdrive_file, sender=Encounter)


class Participation(models.Model):
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
    character = models.ForeignKey(Character, on_delete=models.CASCADE, related_name='participations')
    archetype = models.PositiveSmallIntegerField(choices=ARCHETYPE_CHOICES, db_index=True)
    elite = models.PositiveSmallIntegerField(choices=ELITE_CHOICES, db_index=True)
    party = models.PositiveSmallIntegerField(db_index=True)

    def __str__(self):
        return '%s in %s' % (self.character, self.encounter)

    def data(self):
        return {
                'id': self.encounter.id,
                'url_id': self.encounter.url_id,
                'area': self.encounter.area.name,
                'started_at': self.encounter.started_at,
                'duration': self.encounter.duration,
                'character': self.character.name,
                'account': self.character.account.name,
                'profession': self.character.profession,
                'archetype': self.archetype,
                'elite': self.elite,
                'uploaded_at': self.encounter.uploaded_at,
                'success': self.encounter.success,
                'category': self.encounter.category_id,
                'tags': list(self.encounter.tags.names()),
            }

    class Meta:
        unique_together = ('encounter', 'character')


class EraAreaStore(models.Model):
    era = models.ForeignKey(Era, on_delete=models.CASCADE, related_name="era_area_stores")
    area = models.ForeignKey(Area, on_delete=models.CASCADE, related_name="era_area_stores")
    value = models.TextField(default="{}")

    @property
    def val(self):
        return json_loads(self.value)

    @val.setter
    def val(self, value):
        self.value = json_dumps(value)


class EraUserStore(models.Model):
    era = models.ForeignKey(Era, on_delete=models.CASCADE, related_name="era_user_stores")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="era_user_stores")
    value = models.TextField(default="{}")

    @property
    def val(self):
        return json_loads(self.value)

    @val.setter
    def val(self, value):
        self.value = json_dumps(value)
