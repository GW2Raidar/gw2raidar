"""Boons, and the buff categories shown on the encounter page.

Only the boons are listed here. Every other buff (offensive, support, defensive) comes from the Elite
Insights output of each encounter, together with its name, icon and category; see eiparser/adapter.py.
"""
import re
from enum import IntEnum


class StackType(IntEnum):
    INTENSITY = 0
    DURATION = 1


class BuffType:
    def __init__(self, name, code, skillid, stacking, capacity):
        self.name = name
        self.code = code
        self.skillid = skillid
        self.stacking = stacking
        self.capacity = capacity


# The codes are the names the buffs are stored under (EncounterBuff.name and the statistics), so they
# must not change.
BUFF_TYPES = [
        BuffType('Might', 'might', [740], StackType.INTENSITY, 25),
        BuffType('Quickness', 'quickness', [1187], StackType.DURATION, 5),
        BuffType('Fury', 'fury', [725], StackType.DURATION, 9),
        BuffType('Protection', 'protection', [717], StackType.DURATION, 5),
        BuffType('Alacrity', 'alacrity', [30328], StackType.DURATION, 9),
        BuffType('Resolution', 'resolution', [873], StackType.DURATION, 5),
        BuffType('Regeneration', 'regen', [718], StackType.DURATION, 5),
        BuffType('Aegis', 'aegis', [743], StackType.DURATION, 5),
        BuffType('Resistance', 'resist', [26980], StackType.DURATION, 5),
        BuffType('Stability', 'stab', [1122], StackType.INTENSITY, 25),
        BuffType('Swiftness', 'swift', [719], StackType.DURATION, 9),
        BuffType('Vigor', 'vigor', [726], StackType.DURATION, 5),
        # Replaced in the game by Resolution (same skill ID); only found in encounters uploaded before that
        BuffType('Retaliation', 'retaliation', [], StackType.DURATION, 5),
    ]

BUFFS = {buff.name: buff for buff in BUFF_TYPES}
BUFF_CODES_BY_ID = {skill_id: buff.code for buff in BUFF_TYPES for skill_id in buff.skillid}

BOON_ORDER = [
    'might',
    'fury',
    'quickness',
    'alacrity',
    'protection',
    'resolution',
    'aegis',
    'regen',
    'swift',
    'vigor',
    'resist',
    'stab',
]
# Encounters analysed before the Elite Insights switch have Retaliation where Resolution is now
LEGACY_BOON_ORDER = ['retaliation' if code == 'resolution' else code for code in BOON_ORDER]

# Buff categories, in display order: (Elite Insights classification, tab ID, tab name).
# These are the tabs of the "Buffs" section of an Elite Insights HTML report.
BOONS_TAB = 'boons'
BUFF_CATEGORIES = [
    ('Boon', BOONS_TAB, 'Boons'),
    ('Offensive', 'offensive_buffs', 'Offensive Buffs'),
    ('Support', 'support_buffs', 'Support Buffs'),
    ('Defensive', 'defensive_buffs', 'Defensive Buffs'),
    ('Gear', 'gear_buffs', 'Gear Buffs'),
    ('Condition', 'conditions', 'Conditions'),
    ('Debuff', 'debuffs', 'Debuffs'),
    ('Nourishment', 'nourishments', 'Nourishments'),
    ('Enhancement', 'enhancements', 'Enhancements'),
    ('Other Consumable', 'other_consumables', 'Other Consumables'),
    # everything EI does not classify; mostly profession specific effects, listed by EI as personal buffs
    ('Other', 'personal_buffs', 'Personal Buffs'),
]
# Categories that are stored with each encounter but not shown yet.
# Personal buffs need their own layout, broken out by profession as in the EI report.
HIDDEN_BUFF_TABS = frozenset(['personal_buffs'])

# Tabs that are the same for every encounter; the first is the short list shown on the overview
BUFF_TABS = [
    {
        'name': 'Overview',
        'order': [
            'might',
            'fury',
            'quickness',
            'alacrity',
        ],
    },
    {
        'name': 'Boons',
        'order': BOON_ORDER,
    },
]


def buff_code(skill_id, name):
    """The name a buff is stored under: the fixed code for boons, otherwise derived from the buff's name."""
    code = BUFF_CODES_BY_ID.get(skill_id)
    if code is None:
        code = re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')
    return code
