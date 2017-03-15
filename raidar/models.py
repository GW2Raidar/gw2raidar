from django.db import models
from django.contrib.auth.models import User
from django.core.validators import RegexValidator
from hashlib import md5
import re


# unique to 30-60s precision
START_RESOLUTION = 60



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

    user = models.ForeignKey(User, blank=True, null=True, on_delete=models.CASCADE, related_name='accounts')
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

    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='characters')
    name = models.CharField(max_length=64, db_index=True)
    profession = models.PositiveSmallIntegerField(choices=PROFESSION_CHOICES, db_index=True)
    verified_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    class Meta:
        # name is not necessarily unique, just unique at a time
        unique_together = ('name', 'account', 'profession')
        ordering = ('name',)


class EncounterManager(models.Manager):
    # hash account names at construction
    # (do they need to ever be updated? I don't think so)
    def get_or_create(self, *args, **kwargs):
        account_names = kwargs.pop('account_names', False)
        if account_names:
            kwargs['account_hash'] = Encounter.calculate_account_hash(account_names)
        return super(EncounterManager, self).get_or_create(*args, **kwargs)

class Encounter(models.Model):
    started_at = models.IntegerField(db_index=True)
    area = models.ForeignKey(Area, on_delete=models.PROTECT, related_name='encounters')
    characters = models.ManyToManyField(Character, through='Participation', related_name='encounters')
    dump = models.TextField(editable=False)
    # hack to try to ensure uniqueness
    account_hash = models.CharField(max_length=32, editable=False)
    started_at_full = models.IntegerField(editable=False)
    started_at_half = models.IntegerField(editable=False)
    objects = EncounterManager()

    def __str__(self):
        return '%s (%s)' % (self.area.name, self.started_at)

    def save(self, *args, **kwargs):
        self.started_at_full = round(self.started_at / START_RESOLUTION) * START_RESOLUTION
        self.started_at_half = round((self.started_at + START_RESOLUTION / 2) / START_RESOLUTION) * START_RESOLUTION
        super(Encounter, self).save(*args, **kwargs)

    @staticmethod
    def calculate_account_hash(account_names):
        conc = ':'.join(sorted(account_names))
        hash_object = md5(conc.encode())
        return hash_object.hexdigest()

    class Meta:
        index_together = ('area', 'started_at')
        ordering = ('started_at',)
        unique_together = ('area', 'account_hash', 'started_at_full')
        unique_together = ('area', 'account_hash', 'started_at_half')


class Participation(models.Model):
    POWER = 1
    CONDI = 2
    TANK = 3
    HEAL = 4

    ARCHETYPE_CHOICES = (
            (POWER, "Power"),
            (CONDI, "Condi"),
            (TANK, "Tank"),
            (HEAL, "Heal"),
        )

    encounter = models.ForeignKey(Encounter, on_delete=models.CASCADE, related_name='participations')
    character = models.ForeignKey(Character, on_delete=models.CASCADE, related_name='participations')
    archetype = models.PositiveSmallIntegerField(choices=ARCHETYPE_CHOICES, db_index=True)
    party = models.PositiveSmallIntegerField(db_index=True)

    def __str__(self):
        return '%s in %s' % (self.character, self.encounter)

    class Meta:
        unique_together = ('encounter', 'character')
