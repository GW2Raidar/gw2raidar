"""Encounter table.

Encounters are recognised by Elite Insights; this table maps EI's stable
encounter IDs (``eiEncounterID``, see LogIDs.md in the EI repository) to
the areas the site knows about.

Area IDs:
  * encounters that predate the EI switch keep their original area ID (the
    ArcDPS boss ID), with challenge mode at ``+ 0xFF0000``;
  * encounters added since use the EI encounter ID, with challenge mode at
    ``+ 0x1000000`` and LCM at ``+ 0x2000000``.
"""
from enum import IntEnum


class DesiredValue(IntEnum):
    LOW = -1
    NONE = 0
    HIGH = 1


class MetricType(IntEnum):
    TIME = 0
    COUNT = 1


class Kind(IntEnum):
    RAID = 1
    EASY = 2
    DUMMY = 3
    FRACTAL = 4
    STRIKE = 5


class Mode(IntEnum):
    NORMAL = 0
    CM = 1
    LEGENDARY_CM = 2


# Short tag shown next to the name of an encounter
MODE_TAGS = {Mode.NORMAL: "", Mode.CM: "CM", Mode.LEGENDARY_CM: "LCM"}
MODE_SUFFIXES = {Mode.CM: " (CM)", Mode.LEGENDARY_CM: " (LCM)"}
# Suffix area names stored before the mode flags existed may still carry
OLD_LCM_SUFFIX = " (Legendary CM)"

MINUTES = 60


class Metric:
    def __init__(self, name, short_name, data_type, split_by_player=True, split_by_phase=False,
                 desired=DesiredValue.LOW, long_name=None):
        self.name = name
        self.short_name = short_name
        self.long_name = long_name or name
        self.data_type = data_type
        self.desired = desired
        self.split_by_player = split_by_player
        self.split_by_phase = split_by_phase

    def __repr__(self):
        return "%s (%s, %s)" % (self.name, self.data_type, self.desired)


def mode_area_id(area_id, mode):
    """Area ID of the CM / LCM variant of an encounter."""
    if mode == Mode.NORMAL:
        return area_id
    if area_id < 0x10000:
        # legacy ArcDPS-ID based areas
        return area_id + (0xFF0000 if mode == Mode.CM else 0xFE0000)
    return area_id + (0x1000000 if mode == Mode.CM else 0x2000000)


class Boss:
    """An encounter in one difficulty mode.

    ``name`` is unique and includes the mode ("Cairn (CM)"); ``base_name`` is the name of the boss alone
    ("Cairn"), which is what the site shows next to a tag for the mode.

    ``metrics`` are the mechanics the pre-EI analyser recorded; they are only
    used to label mechanics of encounters parsed before the EI switch.
    Mechanics of EI-parsed encounters are stored with the encounter itself.
    """
    def __init__(self, name, kind, area_id, ei_ids, metrics=None, enrage=None,
                 has_cm=False, has_legendary_cm=False, non_cm_allowed=True, mode=Mode.NORMAL, base_name=None):
        self.name = name
        self.base_name = base_name or name
        self.kind = kind
        self.area_id = area_id
        self.ei_ids = ei_ids if isinstance(ei_ids, (list, tuple)) else [ei_ids]
        self.metrics = [] if metrics is None else metrics
        self.enrage = enrage
        self.has_cm = has_cm
        self.has_legendary_cm = has_legendary_cm
        self.non_cm_allowed = non_cm_allowed
        # encounters that only exist in challenge mode (fractals) have a single area, which is a CM one
        self.mode = mode if non_cm_allowed else Mode.CM

    # kept for code that still expects the old attribute
    @property
    def boss_ids(self):
        return [self.area_id]

    @property
    def tag(self):
        return MODE_TAGS[self.mode]

    def variant(self, mode):
        return Boss(self.name + MODE_SUFFIXES[mode], self.kind, mode_area_id(self.area_id, mode), self.ei_ids,
                    metrics=self.metrics, enrage=self.enrage, mode=mode, base_name=self.name)

    def __repr__(self):
        return "%s (#%d)" % (self.name, self.area_id)


_SAMAROG_METRICS = [
    Metric('Claw', 'Claw', MetricType.COUNT, True, True),
    Metric('Shockwave', 'Shockwave', MetricType.COUNT, True, True),
    Metric('Prisoner Sweep', 'Sweep', MetricType.COUNT, True, True),
    Metric('Charge', 'Charge', MetricType.COUNT, True, False),
    Metric('Anguished Bolt', 'Guldhem Stun', MetricType.COUNT, True, False),
    Metric('Inevitable Betrayal', 'Chose Poorly', MetricType.COUNT, True, False),
    Metric('Bludgeon', 'Bludgeon', MetricType.COUNT, True, False),
    Metric('Fixate', 'Fixate', MetricType.COUNT, True, True),
    Metric('Small Friend', 'Small Friend', MetricType.COUNT, True, True),
    Metric('Big Friend', 'Big Friend', MetricType.COUNT, True, True),
    Metric('Spear Impact', 'Spear Impacts', MetricType.COUNT, True, True),
]

# Base (normal mode) encounters. CM variants are generated below.
BASE_BOSSES = [
    # ---- Raid wings ----
    # W1 Spirit Vale
    Boss('Vale Guardian', Kind.RAID, 0x3C4E, 0x020101, enrage=8 * MINUTES, metrics=[
        Metric('Blue Guardian Invulnerability Time', 'Blue Invuln', MetricType.TIME, False),
        Metric('Bullets Eaten', 'Bulleted', MetricType.COUNT),
        Metric('Teleports', 'Teleported', MetricType.COUNT),
    ]),
    Boss('Gorseval', Kind.RAID, 0x3C45, 0x020102, enrage=7 * MINUTES, metrics=[
        Metric('Unmitigated Spectral Impacts', 'Slammed', MetricType.COUNT, True, True),
        Metric('Ghastly Imprisonments', 'Imprisoned', MetricType.COUNT),
        Metric('Spectral Darkness', 'Tainted', MetricType.TIME),
    ]),
    Boss('Sabetha', Kind.RAID, 0x3C0F, 0x020103, enrage=9 * MINUTES, metrics=[
        Metric('Heavy Bombs Undefused', 'Heavy Bombs', MetricType.COUNT, False),
    ]),
    Boss('Spirit Race', Kind.EASY, 0x020104, 0x020104),
    # W2 Salvation Pass
    Boss('Slothasor', Kind.RAID, 0x3EFB, 0x020201, enrage=7 * MINUTES, metrics=[
        Metric('Tantrum Knockdowns', 'Tantrumed', MetricType.COUNT),
        Metric('Spores Received', 'Spored', MetricType.COUNT),
        Metric('Spores Blocked', 'Spore Blocks', MetricType.COUNT, True, False, DesiredValue.HIGH),
        Metric('Volatile Poison Carrier', 'Poisoned', MetricType.COUNT, True, False, DesiredValue.NONE),
        Metric('Toxic Cloud Breathed', 'Green Goo', MetricType.COUNT, True, False),
    ]),
    Boss('Bandit Trio', Kind.EASY, 0x3ED8, 0x020202, enrage=9 * MINUTES),
    Boss('Matthias', Kind.RAID, 0x3EF3, 0x020203, enrage=10 * MINUTES, metrics=[
        Metric('Moved While Unbalanced', 'Slipped', MetricType.COUNT),
        Metric('Surrender', 'Surrendered', MetricType.COUNT),
        Metric('Burning Stacks Received', 'Burned', MetricType.COUNT, True, True),
        Metric('Corrupted', 'Corrupted', MetricType.COUNT, True, False, DesiredValue.NONE),
        Metric('Matthias Shards Returned', 'Reflected', MetricType.COUNT, False),
        Metric('Shards Absorbed', 'Absorbed', MetricType.COUNT, True, False, DesiredValue.NONE),
        Metric('Sacrificed', 'Sacrificed', MetricType.COUNT, True, False, DesiredValue.NONE),
        Metric('Well of the Profane Carrier', 'Welled', MetricType.COUNT, True, False, DesiredValue.NONE),
    ]),
    # W3 Stronghold of the Faithful
    Boss('Escort', Kind.EASY, 0x020301, 0x020301),
    Boss('Keep Construct', Kind.RAID, 0x3F6B, 0x020302, enrage=10 * MINUTES, has_cm=True, metrics=[
        Metric('Correct Orb', 'Correct Orbs', MetricType.COUNT),
        Metric('Wrong Orb', 'Wrong Orbs', MetricType.COUNT),
        Metric('Rifts Hit', 'Rifts Hit', MetricType.COUNT, False, False, DesiredValue.HIGH),
        Metric('Gaining Power', 'Power Gained', MetricType.COUNT, False, False),
        Metric('Magic Blast Intensity', 'Orbs Missed', MetricType.COUNT, False, False),
    ]),
    Boss('Twisted Castle', Kind.EASY, 0x020303, 0x020303),
    Boss('Xera', Kind.RAID, 0x3F76, 0x020304, enrage=11 * MINUTES, metrics=[
        Metric('Derangement', 'Deranged', MetricType.COUNT),
    ]),
    # W4 Bastion of the Penitent
    Boss('Cairn', Kind.RAID, 0x432A, 0x020401, enrage=8 * MINUTES, has_cm=True, metrics=[
        Metric('Displacement', 'Teleported', MetricType.COUNT),
        Metric('Meteor Swarm', 'Shard Hits', MetricType.COUNT),
        Metric('Spatial Manipulation', 'Circles', MetricType.COUNT),
        Metric('Shared Agony', 'Agony', MetricType.COUNT),
    ]),
    Boss('Mursaat Overseer', Kind.RAID, 0x4314, 0x020402, enrage=6 * MINUTES, has_cm=True, metrics=[
        Metric('Protect', 'Protector', MetricType.COUNT),
        Metric('Claim', 'Claimer', MetricType.COUNT),
        Metric('Dispel', 'Dispeller', MetricType.COUNT),
        Metric('Soldiers', 'Soldiers', MetricType.COUNT, False),
        Metric('Soldier\'s Aura', 'Soldier AOE', MetricType.COUNT),
        Metric('Enemy Tile', 'Enemy Tile', MetricType.COUNT),
    ]),
    Boss('Samarog', Kind.RAID, 0x4324, 0x020403, enrage=11 * MINUTES, has_cm=True, metrics=_SAMAROG_METRICS),
    Boss('Deimos', Kind.RAID, 0x4302, 0x020404, enrage=12 * MINUTES, has_cm=True, metrics=[
        Metric('Annihilate', 'Slammed', MetricType.COUNT, True, False),
        Metric('Soul Feast', 'Hand Touches', MetricType.COUNT, True, False),
        Metric('Mind Crush', 'Mind Crush', MetricType.COUNT, True, False),
        Metric('Rapid Decay', 'Black', MetricType.COUNT, True, False),
        Metric('Demonic Shockwave', 'Shockwave', MetricType.COUNT, True, False),
        Metric('Teleports', 'Teleports', MetricType.COUNT, True, False),
        Metric('Tear Consumed', 'Tears Consumed', MetricType.COUNT, True, False),
    ]),
    # W5 Hall of Chains
    Boss('Soulless Horror', Kind.RAID, 19767, 0x020501, enrage=8 * MINUTES, has_cm=True, metrics=[
        Metric('Inner Vortex', 'Inner Vortex', MetricType.COUNT, True, False),
        Metric('Outer Vortex', 'Outer Vortex', MetricType.COUNT, True, False),
        Metric('Soul Rift', 'Soul Rift', MetricType.COUNT, True, False),
        Metric('Quad Slash', 'Quad Slash', MetricType.COUNT, True, False),
        Metric('Scythe Hits', 'Scythe Hits', MetricType.COUNT, True, False),
        Metric('Necrosis Received', 'Necrosis', MetricType.COUNT, True, False),
    ]),
    Boss('River of Souls', Kind.EASY, 0x020502, 0x020502),
    Boss('Broken King', Kind.RAID, 0x020503, 0x020503),
    Boss('Soul Eater', Kind.RAID, 0x020504, 0x020504),
    Boss('Eyes of Judgement and Fate', Kind.RAID, 0x020505, 0x020505),
    Boss('Dhuum', Kind.RAID, 19450, 0x020506, enrage=10 * MINUTES, has_cm=True, metrics=[
        Metric('Messenger', 'Messenger', MetricType.COUNT, True, False),
        Metric('Shackle Hits', 'Shackle Hits', MetricType.COUNT, True, False),
        Metric('Fissured', 'Fissured', MetricType.COUNT, True, False),
        Metric('Putrid Bomb', 'Putrid Bomb', MetricType.COUNT, True, False),
        Metric('Sucked', 'Sucked', MetricType.COUNT, True, False),
        Metric('Death Marked', 'Death Marked', MetricType.COUNT, True, False),
        Metric('Snatched', 'Snatched', MetricType.COUNT, True, False),
        Metric('Dhuum Gaze', 'Dhuum Gaze', MetricType.COUNT, True, False),
    ]),
    # W6 Mythwright Gambit
    Boss('Conjured Amalgamate', Kind.RAID, 0xABC6, 0x020601, enrage=8 * MINUTES, has_cm=True, metrics=[
        Metric('Pulverize', 'Slammed', MetricType.COUNT, True, False),
        Metric('Junk Fall', 'Falling Junk', MetricType.COUNT, True, False),
        Metric('Junk Absorption', 'Purple Orbs', MetricType.COUNT, True, False),
    ]),
    Boss('Largos Twins', Kind.RAID, 0x5271, 0x020602, enrage=8 * MINUTES, has_cm=True, metrics=[
        Metric('Waterlogged', 'Waterlogged', MetricType.COUNT, True, False),
        Metric('Vapor Rush', 'Charged', MetricType.COUNT, True, False),
        Metric('Geyser', 'Launched (Nikare)', MetricType.COUNT, True, False),
        Metric('Water Bomb', 'Bombed', MetricType.COUNT, True, False),
        Metric('Aquatic Detainment', 'Bubbled', MetricType.COUNT, True, False),
        Metric('Aquatic Aura (Nikare)', 'Aquatic Aura (Nikare)', MetricType.COUNT, True, False),
        Metric('Aquatic Vortex', 'Tornado', MetricType.COUNT, True, False),
        Metric('Sea Swell', 'Launched (Kenut)', MetricType.COUNT, True, False),
        Metric('Vapor Jet', 'Boon Steal', MetricType.COUNT, True, False),
        Metric('Aquatic Aura (Kenut)', 'Aquatic Aura (Kenut)', MetricType.COUNT, True, False),
    ]),
    Boss('Qadim', Kind.RAID, 0x51C6, 0x020603, enrage=13 * MINUTES, has_cm=True, metrics=[
        Metric('Power of the Lamp', 'Lamp', MetricType.COUNT, True, False),
        Metric('Sea of Flame', 'Qadim Hitbox', MetricType.COUNT, True, False),
        Metric('Flame Wave', 'Knockback', MetricType.COUNT, True, False),
        Metric('Fire Wave', 'Shockwave', MetricType.COUNT, True, False),
        Metric('Fiery Dance', 'Fiery Platform Edges', MetricType.COUNT, True, False),
    ]),
    # W7 The Key of Ahdashim
    Boss('Cardinal Adina', Kind.RAID, 22006, 0x020701, enrage=8 * MINUTES, has_cm=True),
    Boss('Cardinal Sabir', Kind.RAID, 21964, 0x020702, enrage=9 * MINUTES, has_cm=True),
    Boss('Qadim the Peerless', Kind.RAID, 22000, 0x020703, enrage=12 * MINUTES, has_cm=True),
    # W8 Mount Balrior
    Boss('Greer, the Blightbringer', Kind.RAID, 0x020801, 0x020801, has_cm=True),
    Boss('Decima, the Stormsinger', Kind.RAID, 0x020802, 0x020802, has_cm=True),
    Boss('Ura, the Steamshrieker', Kind.RAID, 0x020803, 0x020803, has_cm=True, has_legendary_cm=True),

    # ---- Golems (area ID is the ArcDPS species ID) ----
    Boss('Standard Kitty Golem', Kind.DUMMY, 16199, 0x080106),
    Boss('Average Kitty Golem', Kind.DUMMY, 16177, 0x080105),
    Boss('Vital Kitty Golem', Kind.DUMMY, 16198, 0x080104),
    Boss('Massive Standard Kitty Golem', Kind.DUMMY, 16178, 0x080103),
    Boss('Massive Average Kitty Golem', Kind.DUMMY, 16202, 0x080102),
    Boss('Massive Vital Kitty Golem', Kind.DUMMY, 16169, 0x080101),
    Boss('Resistant Kitty Golem', Kind.DUMMY, 16176, 0x080108),
    Boss('Tough Kitty Golem', Kind.DUMMY, 16174, 0x080107),
    Boss('Large Kitty Golem', Kind.DUMMY, 19676, 0x080109),
    Boss('Medium Kitty Golem', Kind.DUMMY, 19645, 0x08010A),

    # ---- Fractals (challenge mode only) ----
    Boss('Skorvald the Shattered', Kind.FRACTAL, 0x44E0, 0x030201, has_cm=True, non_cm_allowed=False),
    Boss('Artsariiv', Kind.FRACTAL, 0x461d, 0x030202, has_cm=True, non_cm_allowed=False),
    Boss('Arkk', Kind.FRACTAL, 0x455f, 0x030203, has_cm=True, non_cm_allowed=False),
    Boss('MAMA', Kind.FRACTAL, 0x427d, 0x030101, has_cm=True, non_cm_allowed=False),
    Boss('Siax', Kind.FRACTAL, 0x4284, 0x030102, has_cm=True, non_cm_allowed=False),
    Boss('Ensolyss', Kind.FRACTAL, 0x4234, 0x030103, has_cm=True, non_cm_allowed=False),
    Boss('Ai, Keeper of the Peak', Kind.FRACTAL, 0x030301, 0x030301, has_cm=True, non_cm_allowed=False),
    Boss('Elemental Ai', Kind.FRACTAL, 0x030302, 0x030302, has_cm=True, non_cm_allowed=False),
    Boss('Dark Ai', Kind.FRACTAL, 0x030303, 0x030303, has_cm=True, non_cm_allowed=False),
    Boss('Kanaxai, Scythe of House Aurkus', Kind.FRACTAL, 0x030401, 0x030401, has_cm=True, non_cm_allowed=False),
    Boss('Cerus and Deimos', Kind.FRACTAL, 0x030501, 0x030501, has_cm=True, non_cm_allowed=False),
    Boss('Eparch', Kind.FRACTAL, 0x030502, 0x030502, has_cm=True, non_cm_allowed=False),
    Boss('Whispering Shadow', Kind.FRACTAL, 0x030601, 0x030601, has_cm=True, non_cm_allowed=False),
    Boss('The Eternal Tyrant', Kind.FRACTAL, 0x030701, 0x030701, has_cm=True, non_cm_allowed=False),

    # ---- Raid encounters (former strike missions) ----
    Boss('Freezie', Kind.STRIKE, 0x040101, 0x040101),
    Boss('Icebrood Construct', Kind.STRIKE, 0x040201, 0x040201),
    Boss('Fraenir of Jormag', Kind.STRIKE, 0x040202, 0x040202),
    Boss('Voice and Claw of the Fallen', Kind.STRIKE, 0x040203, 0x040203),
    Boss('Boneskinner', Kind.STRIKE, 0x040204, 0x040204),
    Boss('Whisper of Jormag', Kind.STRIKE, 0x040205, 0x040205),
    Boss('Varinia Stormsounder', Kind.STRIKE, 0x040206, 0x040206),
    Boss('Aetherblade Hideout', Kind.STRIKE, 0x040301, 0x040301, has_cm=True),
    Boss('Xunlai Jade Junkyard', Kind.STRIKE, 0x040302, 0x040302, has_cm=True),
    Boss('Kaineng Overlook', Kind.STRIKE, 0x040303, 0x040303, has_cm=True),
    Boss('Harvest Temple', Kind.STRIKE, 0x040304, 0x040304, has_cm=True),
    Boss('Old Lion\'s Court', Kind.STRIKE, 0x040305, 0x040305, has_cm=True),
    Boss('Cosmic Observatory', Kind.STRIKE, 0x040501, 0x040501, has_cm=True),
    Boss('Temple of Febe', Kind.STRIKE, 0x040502, 0x040502, has_cm=True, has_legendary_cm=True),
    Boss('Guardian\'s Glade', Kind.STRIKE, 0x040601, 0x040601, has_cm=True),
    Boss('Nexus of Eternity', Kind.STRIKE, 0x040602, 0x040602, has_cm=True, has_legendary_cm=True),
]

BOSS_ARRAY = []
for _boss in BASE_BOSSES:
    BOSS_ARRAY.append(_boss)
    if _boss.non_cm_allowed:
        if _boss.has_cm:
            BOSS_ARRAY.append(_boss.variant(Mode.CM))
        if _boss.has_legendary_cm:
            BOSS_ARRAY.append(_boss.variant(Mode.LEGENDARY_CM))

BOSSES = {boss.area_id: boss for boss in BOSS_ARRAY}
IDS = {boss.name: boss.area_id for boss in BOSS_ARRAY}
EI_BOSSES = {ei_id: boss for boss in BASE_BOSSES for ei_id in boss.ei_ids}

assert len(BOSSES) == len(BOSS_ARRAY), "duplicate area ID in boss table"
assert len(IDS) == len(BOSS_ARRAY), "duplicate name in boss table"


def area_name_and_mode(area_id, stored_name):
    """Returns (name of the boss alone, Mode) for an area, given its ID and a name that may include the mode.

    Areas that are no longer in the boss table are recognised by the mode suffix of their name.
    """
    boss = BOSSES.get(area_id)
    if boss is not None:
        return boss.base_name, boss.mode
    for mode, suffix in list(MODE_SUFFIXES.items()) + [(Mode.LEGENDARY_CM, OLD_LCM_SUFFIX)]:
        if stored_name.endswith(suffix):
            return stored_name[:-len(suffix)], mode
    return stored_name, Mode.NORMAL


class UnsupportedEncounter(Exception):
    pass


def find_boss(ei_id, is_cm=False, is_legendary_cm=False):
    """Returns the Boss entry (in the right difficulty mode) for an EI encounter ID.

    Raises UnsupportedEncounter with a user-presentable message otherwise.
    """
    base = EI_BOSSES.get(ei_id)
    if base is None:
        raise UnsupportedEncounter("This encounter is not supported")

    if not base.non_cm_allowed:
        # CM-only encounters live in a single area
        if not (is_cm or is_legendary_cm):
            raise UnsupportedEncounter("Only cm encounters allowed for {}".format(base.name))
        return base

    mode = Mode.LEGENDARY_CM if is_legendary_cm else Mode.CM if is_cm else Mode.NORMAL
    if mode == Mode.LEGENDARY_CM and not base.has_legendary_cm:
        mode = Mode.CM
    if mode == Mode.CM and not base.has_cm:
        mode = Mode.NORMAL
    return BOSSES[mode_area_id(base.area_id, mode)]


BOSS_LOCATIONS = [
    {
        "name": "Raids",
        "all": 'All raid bosses',
        "columns": 3,
        "wings": [
            {
                "name": "Spirit Vale",
                "bosses": [
                    IDS['Vale Guardian'],
                    IDS['Spirit Race'],
                    IDS['Gorseval'],
                    IDS['Sabetha'],
                ],
            },
            {
                "name": "Salvation Pass",
                "bosses": [
                    IDS['Slothasor'],
                    IDS['Bandit Trio'],
                    IDS['Matthias'],
                ],
            },
            {
                "name": "Stronghold of the Faithful",
                "bosses": [
                    IDS['Escort'],
                    IDS['Keep Construct'],
                    IDS['Twisted Castle'],
                    IDS['Xera'],
                ],
            },
            {
                "name": "Bastion of the Penitent",
                "bosses": [
                    IDS['Cairn'],
                    IDS['Mursaat Overseer'],
                    IDS['Samarog'],
                    IDS['Deimos'],
                ],
            },
            {
                "name": "Hall of Chains",
                "bosses": [
                    IDS['Soulless Horror'],
                    IDS['River of Souls'],
                    IDS['Broken King'],
                    IDS['Soul Eater'],
                    IDS['Eyes of Judgement and Fate'],
                    IDS['Dhuum'],
                ],
            },
            {
                "name": "Mythwright Gambit",
                "bosses": [
                    IDS['Conjured Amalgamate'],
                    IDS['Largos Twins'],
                    IDS['Qadim'],
                ],
            },
            {
                "name": "The Key of Ahdashim",
                "bosses": [
                    IDS['Cardinal Adina'],
                    IDS['Cardinal Sabir'],
                    IDS['Qadim the Peerless'],
                ],
            },
            {
                "name": "Mount Balrior",
                "bosses": [
                    IDS['Greer, the Blightbringer'],
                    IDS['Decima, the Stormsinger'],
                    IDS['Ura, the Steamshrieker'],
                ],
            },
        ],
    },
    {
        "name": "CM Raids",
        # "all": 'All raid bosses',
        "columns": 3,
        "wings": [
            {
                "name": "Stronghold of the Faithful",
                "bosses": [
                    IDS['Keep Construct (CM)'],
                ],
            },
            {
                "name": "Bastion of the Penitent",
                "bosses": [
                    IDS['Cairn (CM)'],
                    IDS['Mursaat Overseer (CM)'],
                    IDS['Samarog (CM)'],
                    IDS['Deimos (CM)'],
                ],
            },
            {
                "name": "Hall of Chains",
                "bosses": [
                    IDS['Soulless Horror (CM)'],
                    IDS['Dhuum (CM)'],
                ],
            },
            {
                "name": "Mythwright Gambit",
                "bosses": [
                    IDS['Conjured Amalgamate (CM)'],
                    IDS['Largos Twins (CM)'],
                    IDS['Qadim (CM)'],
                ],
            },
            {
                "name": "The Key of Ahdashim",
                "bosses": [
                    IDS['Cardinal Adina (CM)'],
                    IDS['Cardinal Sabir (CM)'],
                    IDS['Qadim the Peerless (CM)'],
                ],
            },
            {
                "name": "Mount Balrior",
                "bosses": [
                    IDS['Greer, the Blightbringer (CM)'],
                    IDS['Decima, the Stormsinger (CM)'],
                    IDS['Ura, the Steamshrieker (CM)'],
                    IDS['Ura, the Steamshrieker (LCM)'],
                ],
            },
        ],
    },
    {
        "name": "CM Fractals",
        "all": 'All fractal bosses',
        "columns": 4,
        "wings": [
            {
                "name": "Nightmare",
                "bosses": [
                    IDS['MAMA'],
                    IDS['Siax'],
                    IDS['Ensolyss'],
                ],
            },
            {
                "name": "Shattered Observatory",
                "bosses": [
                    IDS['Skorvald the Shattered'],
                    IDS['Artsariiv'],
                    IDS['Arkk'],
                ],
            },
            {
                "name": "Sunqua Peak",
                "bosses": [
                    IDS['Ai, Keeper of the Peak'],
                    IDS['Elemental Ai'],
                    IDS['Dark Ai'],
                ],
            },
            {
                "name": "Silent Surf",
                "bosses": [
                    IDS['Kanaxai, Scythe of House Aurkus'],
                ],
            },
            {
                "name": "Lonely Tower",
                "bosses": [
                    IDS['Cerus and Deimos'],
                    IDS['Eparch'],
                ],
            },
            {
                "name": "Kinfall",
                "bosses": [
                    IDS['Whispering Shadow'],
                ],
            },
            {
                "name": "Solitary Throne",
                "bosses": [
                    IDS['The Eternal Tyrant'],
                ],
            },
        ],
    },
    # Appended after the original three: the leaderboard "kind" is an index into this list
    {
        "name": "Raid Encounters",
        "columns": 3,
        "wings": [
            {
                "name": "Festivals",
                "bosses": [
                    IDS['Freezie'],
                ],
            },
            {
                "name": "Icebrood Saga",
                "bosses": [
                    IDS['Icebrood Construct'],
                    IDS['Voice and Claw of the Fallen'],
                    IDS['Fraenir of Jormag'],
                    IDS['Boneskinner'],
                    IDS['Whisper of Jormag'],
                    IDS['Varinia Stormsounder'],
                ],
            },
            {
                "name": "End of Dragons",
                "bosses": [
                    IDS['Aetherblade Hideout'],
                    IDS['Xunlai Jade Junkyard'],
                    IDS['Kaineng Overlook'],
                    IDS['Harvest Temple'],
                    IDS['Old Lion\'s Court'],
                ],
            },
            {
                "name": "Secrets of the Obscure",
                "bosses": [
                    IDS['Cosmic Observatory'],
                    IDS['Temple of Febe'],
                ],
            },
            {
                "name": "Visions of Eternity",
                "bosses": [
                    IDS['Guardian\'s Glade'],
                    IDS['Nexus of Eternity'],
                ],
            },
        ],
    },
    {
        "name": "CM Raid Encounters",
        "columns": 3,
        "wings": [
            {
                "name": "End of Dragons",
                "bosses": [
                    IDS['Aetherblade Hideout (CM)'],
                    IDS['Xunlai Jade Junkyard (CM)'],
                    IDS['Kaineng Overlook (CM)'],
                    IDS['Harvest Temple (CM)'],
                    IDS['Old Lion\'s Court (CM)'],
                ],
            },
            {
                "name": "Secrets of the Obscure",
                "bosses": [
                    IDS['Cosmic Observatory (CM)'],
                    IDS['Temple of Febe (CM)'],
                    IDS['Temple of Febe (LCM)'],
                ],
            },
            {
                "name": "Visions of Eternity",
                "bosses": [
                    IDS['Guardian\'s Glade (CM)'],
                    IDS['Nexus of Eternity (CM)'],
                    IDS['Nexus of Eternity (LCM)'],
                ],
            },
        ],
    },
]
