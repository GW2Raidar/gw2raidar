from django.db import models
from django.contrib.auth.models import User
from django.core.validators import RegexValidator
import re




class Area(models.Model):
    id = models.IntegerField(primary_key=True)
    name = models.CharField(max_length=64, unique=True)

    def __str__(self):
        return self.name


class Account(models.Model):
    ACCOUNT_NAME_RE = re.compile(r'\S+\.\d{4}') # TODO make more restrictive?
    API_KEY_RE = re.compile(
            r'-'.join(r'[0-9A-F]{%d}' % n for n in (8, 4, 4, 4, 20, 4, 4, 4, 12)) + r'$',
            re.IGNORECASE)

    user = models.ForeignKey(User, blank=True, null=True, on_delete=models.CASCADE)
    name = models.CharField(max_length=64, unique=True, validators=[RegexValidator(ACCOUNT_NAME_RE)])
    api_key = models.CharField('API key', max_length=72, blank=True, validators=[RegexValidator(API_KEY_RE)])

    def __str__(self):
        return self.name


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

    account = models.ForeignKey(Account, on_delete=models.CASCADE)
    name = models.CharField(max_length=64, db_index=True)
    profession = models.PositiveSmallIntegerField(choices=PROFESSION_CHOICES, db_index=True)
    verified_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    class Meta:
        # name is not necessarily unique, just unique at a time
        unique_together = ('name', 'verified_at')


class Encounter(models.Model):
    started_at = models.DateTimeField(db_index=True)
    area = models.ForeignKey(Area, on_delete=models.PROTECT)
    # XXX https://docs.djangoproject.com/en/1.10/topics/db/examples/many_to_many/
    characters = models.ManyToManyField(Character, related_name="encounters")

    def __str__(self):
        return '%s (%s)' % (self.area.name, self.started_at)

    class Meta:
        index_together = ('area', 'started_at')
