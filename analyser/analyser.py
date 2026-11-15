"""Shared enums and lookup tables.

Log parsing and stat computation are done by Elite Insights (see the
``eiparser`` package); this module only keeps the definitions the rest of
the site (models, views, migrations) refers to.
"""
from enum import IntEnum
from .bosses import *


class Archetype(IntEnum):
    POWER = 1
    CONDI = 2
    TANK = 3
    HEAL = 4
    SUPPORT = 5


class Elite(IntEnum):
    CORE = 0
    HEART_OF_THORNS = 1
    PATH_OF_FIRE = 2
    END_OF_DRAGONS = 3
    VISIONS_OF_ETERNITY = 4


class Profession(IntEnum):
    GUARDIAN = 1
    WARRIOR = 2
    ENGINEER = 3
    RANGER = 4
    THIEF = 5
    ELEMENTALIST = 6
    MESMER = 7
    NECROMANCER = 8
    REVENANT = 9


SPECIALISATIONS = {
    (Profession.GUARDIAN, 0): "Guardian",
    (Profession.WARRIOR, 0): "Warrior",
    (Profession.ENGINEER, 0): "Engineer",
    (Profession.RANGER, 0): "Ranger",
    (Profession.THIEF, 0): "Thief",
    (Profession.ELEMENTALIST, 0): "Elementalist",
    (Profession.MESMER, 0): "Mesmer",
    (Profession.NECROMANCER, 0): "Necromancer",
    (Profession.REVENANT, 0): "Revenant",

    (Profession.GUARDIAN, 1): 'Dragonhunter',
    (Profession.WARRIOR, 1): 'Berserker',
    (Profession.ENGINEER, 1): 'Scrapper',
    (Profession.RANGER, 1): 'Druid',
    (Profession.THIEF, 1): 'Daredevil',
    (Profession.ELEMENTALIST, 1): 'Tempest',
    (Profession.MESMER, 1): 'Chronomancer',
    (Profession.NECROMANCER, 1): 'Reaper',
    (Profession.REVENANT, 1): 'Herald',

    (Profession.GUARDIAN, 2): 'Firebrand',
    (Profession.WARRIOR, 2): 'Spellbreaker',
    (Profession.ENGINEER, 2): 'Holosmith',
    (Profession.RANGER, 2): 'Soulbeast',
    (Profession.THIEF, 2): 'Deadeye',
    (Profession.ELEMENTALIST, 2): 'Weaver',
    (Profession.MESMER, 2): 'Mirage',
    (Profession.NECROMANCER, 2): 'Scourge',
    (Profession.REVENANT, 2): 'Renegade',

    (Profession.GUARDIAN, 3): 'Willbender',
    (Profession.WARRIOR, 3): 'Bladesworn',
    (Profession.ENGINEER, 3): 'Mechanist',
    (Profession.RANGER, 3): 'Untamed',
    (Profession.THIEF, 3): 'Specter',
    (Profession.ELEMENTALIST, 3): 'Catalyst',
    (Profession.MESMER, 3): 'Virtuoso',
    (Profession.NECROMANCER, 3): 'Harbinger',
    (Profession.REVENANT, 3): 'Vindicator',

    (Profession.GUARDIAN, 4): 'Luminary',
    (Profession.WARRIOR, 4): 'Paragon',
    (Profession.ENGINEER, 4): 'Amalgam',
    (Profession.RANGER, 4): 'Galeshot',
    (Profession.THIEF, 4): 'Antiquary',
    (Profession.ELEMENTALIST, 4): 'Evoker',
    (Profession.MESMER, 4): 'Troubadour',
    (Profession.NECROMANCER, 4): 'Ritualist',
    (Profession.REVENANT, 4): 'Conduit',
}

# Elite Insights reports a player's specialisation by name
SPECIALISATION_BY_NAME = {name: key for key, name in SPECIALISATIONS.items()}


class EvtcAnalysisException(BaseException):
    pass
