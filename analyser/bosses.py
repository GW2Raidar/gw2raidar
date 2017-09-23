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


class Metric:
    def __init__(self, name, short_name, data_type, split_by_player = True, split_by_phase = False, desired = DesiredValue.LOW):
        self.name = name
        self.short_name = short_name
        self.long_name = name # TODO
        self.data_type = data_type
        self.desired = desired
        self.split_by_player = split_by_player
        self.split_by_phase = split_by_phase

    def __repr__(self):
        return "%s (%s, %s)" % (self.name, self.data_type, self.desired)

class Boss:
    def __init__(self, name, kind, boss_ids, metrics=None, sub_boss_ids=None, key_npc_ids = None, phases=None, despawns_instead_of_dying = False, has_structure_boss = False, success_health_limit = None):
        self.name = name
        self.kind = kind
        self.boss_ids = boss_ids
        self.metrics = [] if metrics is None else metrics
        self.sub_boss_ids = [] if sub_boss_ids is None else sub_boss_ids
        self.phases = [] if phases is None else phases
        self.key_npc_ids = [] if key_npc_ids is None else key_npc_ids
        self.despawns_instead_of_dying = despawns_instead_of_dying
        self.has_structure_boss = has_structure_boss
        self.success_health_limit = success_health_limit

class Phase:
    def __init__(self, name, important,
                 phase_end_damage_stop=None,
                 phase_end_damage_start=None,
                 phase_end_health=None):
        self.name = name
        self.important = important
        self.phase_end_damage_stop = phase_end_damage_stop
        self.phase_end_damage_start = phase_end_damage_start
        self.phase_end_health = phase_end_health

    def find_end_time(self,
                      current_time,
                      damage_gaps,
                      health_updates,
                      skill_activations):
        end_time = None
        if self.phase_end_health is not None:
            relevant_health_updates = health_updates[(health_updates.time >= current_time) &
                                                     (health_updates.dst_agent >= self.phase_end_health * 100)]
            if relevant_health_updates.empty or health_updates['dst_agent'].min() > (self.phase_end_health + 2) * 100:
                return None
            end_time = current_time = int(relevant_health_updates['time'].iloc[-1])
            print("{0}: Detected health below {1} at time {2}".format(self.name, self.phase_end_health, current_time))

        if self.phase_end_damage_stop is not None:
            relevant_gaps = damage_gaps[(damage_gaps.time - damage_gaps.delta >= current_time) &
                                        (damage_gaps.delta > self.phase_end_damage_stop)]
            if not relevant_gaps.empty:
                end_time = current_time = int(relevant_gaps['time'].iloc[0] - relevant_gaps['delta'].iloc[0])
            elif len(damage_gaps.time) > 0 and int(damage_gaps.time.iloc[-1]) >= current_time:
                end_time = current_time = int(damage_gaps.time.iloc[-1])
            else:
                return None

            print("{0}: Detected gap of at least {1} at time {2}".format(self.name, self.phase_end_damage_stop, current_time))

        if self.phase_end_damage_start is not None:
            relevant_gaps = damage_gaps[(damage_gaps.time >= current_time) &
                                        (damage_gaps.delta > self.phase_end_damage_start)]
            if relevant_gaps.empty:
                return None
            end_time = current_time = int(relevant_gaps['time'].iloc[0])
            print("{0}: Detected gap of at least {1} ending at time {2}".format(self.name, self.phase_end_damage_start, current_time))
        return end_time

BOSS_ARRAY = [
    Boss('Vale Guardian', Kind.RAID, [0x3C4E], phases = [
        Phase("Phase 1", True, phase_end_health = 66, phase_end_damage_stop = 10000),
        Phase("First split", False, phase_end_damage_start = 10000),
        Phase("Phase 2", True, phase_end_health = 33, phase_end_damage_stop = 10000),
        Phase("Second split", False, phase_end_damage_start = 10000),
        Phase("Phase 3", True)
    ], metrics = [
        Metric('Blue Guardian Invulnerability Time', 'Blue Invuln', MetricType.TIME, False),
        Metric('Bullets Eaten', 'Bulleted', MetricType.COUNT),
        Metric('Teleports', 'Teleported', MetricType.COUNT)
    ]),
    Boss('Gorseval', Kind.RAID, [0x3C45], phases = [
        Phase("Phase 1", True, phase_end_health = 66, phase_end_damage_stop = 10000),
        Phase("First souls", False, phase_end_damage_start = 10000),
        Phase("Phase 2", True, phase_end_health = 33, phase_end_damage_stop = 10000),
        Phase("Second souls", False, phase_end_damage_start = 10000),
        Phase("Phase 3", True)
    ], metrics = [
        Metric('Unmitigated Spectral Impacts', 'Slammed', MetricType.COUNT, True, True),
        Metric('Ghastly Imprisonments', 'Imprisoned', MetricType.COUNT),
        Metric('Spectral Darkness', 'Tainted', MetricType.TIME)
    ]),
    Boss('Sabetha', Kind.RAID, [0x3C0F], phases = [
        Phase("Phase 1", True, phase_end_health = 75, phase_end_damage_stop = 10000),
        Phase("Kernan", False, phase_end_damage_start = 10000),
        Phase("Phase 2", True, phase_end_health = 50, phase_end_damage_stop = 10000),
        Phase("Knuckles", False, phase_end_damage_start = 10000),
        Phase("Phase 3", True, phase_end_health = 25, phase_end_damage_stop = 10000),
        Phase("Karde", False, phase_end_damage_start = 10000),
        Phase("Phase 4", True)
    ], metrics = [
        Metric('Heavy Bombs Undefused', 'Heavy Bombs', MetricType.COUNT, False)
    ]),
    Boss('Slothasor', Kind.RAID, [0x3EFB], phases = [
        Phase("Phase 1", True, phase_end_health = 80, phase_end_damage_stop = 1000),
        Phase("Break 1", False, phase_end_damage_start = 1000),
        Phase("Phase 2", True, phase_end_health = 60, phase_end_damage_stop = 1000),
        Phase("Break 2", False, phase_end_damage_start = 1000),
        Phase("Phase 3", True, phase_end_health = 40, phase_end_damage_stop = 1000),
        Phase("Break 3", False, phase_end_damage_start = 1000),
        Phase("Phase 4", True, phase_end_health = 20, phase_end_damage_stop = 1000),
        Phase("Break 4", False, phase_end_damage_start = 1000),
        Phase("Phase 5", True, phase_end_health = 10, phase_end_damage_stop = 1000),
        Phase("Break 5", False, phase_end_damage_start = 1000),
        Phase("Phase 6", True)
    ], metrics = [
        Metric('Tantrum Knockdowns', 'Tantrumed', MetricType.COUNT),
        Metric('Spores Received', 'Spored', MetricType.COUNT),
        Metric('Spores Blocked', 'Spore Blocks', MetricType.COUNT, True, False, DesiredValue.HIGH),
        Metric('Volatile Poison Carrier', 'Poisoned', MetricType.COUNT, True, False, DesiredValue.NONE),
        Metric('Toxic Cloud Breathed', 'Green Goo', MetricType.COUNT, True, False)
    ]),
    Boss('Bandit Trio', Kind.EASY, [0x3ED8, 0x3F09, 0x3EFD], phases = [
        #Needs to be a little bit more robust, but it's trio - not the most important fight.
        #Phase("Clear 1", False, phase_end_health = 99),
        Phase("Berg", True, phase_end_damage_stop = 10000),
        Phase("Clear 2", False, phase_end_damage_start= 10000),
        Phase("Zane", True, phase_end_damage_stop = 10000),
        Phase("Clear 3", False, phase_end_damage_start = 10000),
        Phase("Narella", True, phase_end_damage_stop = 10000)
    ]),
    Boss('Matthias', Kind.RAID, [0x3EF3], phases = [
        #Will currently detect phases slightly early - but probably not a big deal?
        Phase("Ice", True, phase_end_health = 80),
        Phase("Fire", True, phase_end_health = 60),
        Phase("Rain", True, phase_end_health = 40),
        Phase("Abomination", True)
    ], metrics = [
        Metric('Moved While Unbalanced', 'Slipped', MetricType.COUNT),
        Metric('Surrender', 'Surrendered', MetricType.COUNT),
        Metric('Burning Stacks Received', 'Burned', MetricType.COUNT, True, True),
        Metric('Corrupted', 'Corrupted', MetricType.COUNT, True, False, DesiredValue.NONE),
        Metric('Matthias Shards Returned', 'Reflected', MetricType.COUNT, False),
        Metric('Shards Absorbed', 'Absorbed', MetricType.COUNT, True, False, DesiredValue.NONE),
        Metric('Sacrificed', 'Sacrificed', MetricType.COUNT, True, False, DesiredValue.NONE),
        Metric('Well of the Profane Carrier', 'Welled', MetricType.COUNT, True, False, DesiredValue.NONE)
    ]),
    Boss('Keep Construct', Kind.RAID, [0x3F6B], phases = [
        # Needs more robust sub-phase mechanisms, but this should be on par with raid-heroes.
        Phase("Pre-burn 1", True, phase_end_damage_stop = 15000),
        Phase("Split 1", False, phase_end_damage_start = 15000),
        Phase("Burn 1", True, phase_end_health = 66, phase_end_damage_stop = 15000),
        Phase("Pacman 1", False, phase_end_damage_start = 15000),
        Phase("Pre-burn 2", True, phase_end_damage_stop = 15000),
        Phase("Split 2", False, phase_end_damage_start = 15000),
        Phase("Burn 2", True, phase_end_health = 33, phase_end_damage_stop = 15000),
        Phase("Pacman 2", False, phase_end_damage_start = 15000),
        Phase("Pre-burn 3", True, phase_end_damage_stop = 18000),
        Phase("Split 3", False, phase_end_damage_start = 18000),
        Phase("Burn 3", True)
    ], metrics = [
        Metric('Correct Orb', 'Correct Orbs', MetricType.COUNT),
        Metric('Wrong Orb', 'Wrong Orbs', MetricType.COUNT),
        Metric('Rifts Hit', 'Rifts Hit', MetricType.COUNT, False, False, DesiredValue.HIGH),
        Metric('Gaining Power', 'Power Gained', MetricType.COUNT, False, False),
        Metric('Magic Blast Intensity', 'Orbs Missed', MetricType.COUNT, False, False)
    ]),
    Boss('Xera', Kind.RAID, [0x3F76, 0x3F9E], despawns_instead_of_dying = True, success_health_limit = 3, phases = [
        Phase("Phase 1", True, phase_end_health = 51, phase_end_damage_stop = 30000),
        Phase("Leyline", False, phase_end_damage_start = 30000),
        Phase("Phase 2", True),
    ], metrics = [
        Metric('Derangement', 'Deranged', MetricType.COUNT)
    ]),
    Boss('Cairn', Kind.RAID, [0x432A], metrics = [
        Metric('Displacement', 'Teleported', MetricType.COUNT),
        Metric('Meteor Swarm', 'Shard Hits', MetricType.COUNT),
        Metric('Spatial Manipulation', 'Circles', MetricType.COUNT),
        Metric('Shared Agony', 'Agony', MetricType.COUNT)
    ]),
    Boss('Mursaat Overseer', Kind.RAID, [0x4314], metrics = [
        Metric('Protect', 'Protector', MetricType.COUNT),
        Metric('Claim', 'Claimer', MetricType.COUNT),
        Metric('Dispel', 'Dispeller', MetricType.COUNT),
        Metric('Soldiers', 'Soldiers', MetricType.COUNT, False),
        Metric('Soldier\'s Aura', 'Soldier AOE', MetricType.COUNT),
        Metric('Enemy Tile', 'Enemy Tile', MetricType.COUNT)
    ]),
    Boss('Samarog', Kind.RAID, [0x4324], phases = [
        Phase("Phase 1", True, phase_end_health = 66, phase_end_damage_stop = 10000),
        Phase("First split", False, phase_end_damage_start = 10000),
        Phase("Phase 2", True, phase_end_health = 33, phase_end_damage_stop = 10000),
        Phase("Second split", False, phase_end_damage_start = 10000),
        Phase("Phase 3", True, phase_end_health=1)
    ], metrics = [
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
        Metric('Spear Impact', 'Spear Impacts', MetricType.COUNT, True, True)
    ]),
    Boss('Deimos', Kind.RAID, [0x4302], key_npc_ids=[17126], despawns_instead_of_dying = True, has_structure_boss = True, phases = [
        Phase("Phase 1", True, phase_end_health = 10, phase_end_damage_stop = 20000),
        Phase("Phase 2", True)
    ], metrics = [
        Metric('Annihilate', 'Slammed', MetricType.COUNT, True, False),
        Metric('Soul Feast', 'Hand Touches', MetricType.COUNT, True, False),
        Metric('Mind Crush', 'Mind Crush', MetricType.COUNT, True, False),
        Metric('Rapid Decay', 'Black', MetricType.COUNT, True, False),
        Metric('Demonic Shockwave', 'Shockwave', MetricType.COUNT, True, False),
        Metric('Teleports', 'Teleports', MetricType.COUNT, True, False),
        Metric('Tear Consumed', 'Tears Consumed', MetricType.COUNT, True, False)
    ]),
    Boss('Standard Kitty Golem', Kind.DUMMY, [16199]),
    Boss('Average Kitty Golem', Kind.DUMMY, [16177]),
    Boss('Vital Kitty Golem', Kind.DUMMY, [16198]),
    Boss('Massive Standard Kitty Golem', Kind.DUMMY, [16178]),
    Boss('Massive Average Kitty Golem', Kind.DUMMY, [16202]),
    Boss('Massive Vital Kitty Golem', Kind.DUMMY, [16169]),
    Boss('Resistant Kitty Golem', Kind.DUMMY, [16176]),
    Boss('Tough Kitty Golem', Kind.DUMMY, [16174]),
    Boss('Skorvald the Shattered (CM)', Kind.FRACTAL,[0x44E0], phases = [
        Phase("Phase 1", True, phase_end_health = 66, phase_end_damage_stop = 15000),
        Phase("First split", False, phase_end_damage_start = 15000),
        Phase("Phase 2", True, phase_end_health = 33, phase_end_damage_stop = 15000),
        Phase("Second split", False, phase_end_damage_start = 15000),
        Phase("Phase 3", True, phase_end_health=1)
    ]),
    Boss('Artsariiv (CM)', Kind.FRACTAL, [0x461d], despawns_instead_of_dying = True, success_health_limit = 3, phases = [
        Phase("Phase 1", True, phase_end_health = 66, phase_end_damage_stop = 10000),
        Phase("First split", False, phase_end_damage_start = 10000),
        Phase("Phase 2", True, phase_end_health = 33, phase_end_damage_stop = 10000),
        Phase("Second split", False, phase_end_damage_start = 10000),
        Phase("Phase 3", True, phase_end_health=1)
    ]),
    Boss('Arkk (CM)', Kind.FRACTAL,[0x455f], despawns_instead_of_dying = True, success_health_limit = 3, phases =[
        Phase("100-80", True, phase_end_health = 80, phase_end_damage_stop = 10000),
        Phase("First orb", False, phase_end_damage_start = 10000),
        Phase("80-70", True, phase_end_health = 70, phase_end_damage_stop = 10000),
        Phase("Archdiviner", False, phase_end_damage_start = 10000),
        Phase("70-50", True, phase_end_health = 50, phase_end_damage_stop = 10000),
        Phase("Second orb", False, phase_end_damage_start = 10000),
        Phase("50-40", True, phase_end_health = 40, phase_end_damage_stop = 10000),
        Phase("Gladiator", False, phase_end_damage_start = 10000),
        Phase("40-30", True, phase_end_health = 30, phase_end_damage_stop = 10000),
        Phase("Third orb", False, phase_end_damage_start = 10000),
        Phase("30-0", True, phase_end_health = 1, phase_end_damage_stop = 10000)
    ]),
    Boss('MAMA (CM)', Kind.FRACTAL, [0x427d], phases = [
        Phase("Phase 1", True, phase_end_health = 75, phase_end_damage_stop = 3000),
        Phase("First split", False, phase_end_damage_start = 3000),
        Phase("Phase 2", True, phase_end_health = 50, phase_end_damage_stop = 3000),
        Phase("Second split", False, phase_end_damage_start = 3000),
        Phase("Phase 3", True, phase_end_health = 25, phase_end_damage_stop = 3000),
        Phase("Second split", False, phase_end_damage_start = 3000),
        Phase("Phase 4", True, phase_end_health=1)
    ]),
    Boss('Siax (CM)', Kind.FRACTAL,[0x4284], phases = [
        Phase("Phase 1", True, phase_end_health = 66, phase_end_damage_stop = 15000),
        Phase("First split", False, phase_end_damage_start = 15000),
        Phase("Phase 2", True, phase_end_health = 33, phase_end_damage_stop = 15000),
        Phase("Second split", False, phase_end_damage_start = 15000),
        Phase("Phase 3", True, phase_end_health=1)
    ]),
    Boss('Ensolyss (CM)', Kind.FRACTAL,[0x4234], phases = [
        Phase("Phase 1", True, phase_end_health = 66, phase_end_damage_stop = 15000),
        Phase("First split", False, phase_end_damage_start = 15000),
        Phase("Phase 2", True, phase_end_health = 33, phase_end_damage_stop = 15000),
        Phase("Second split", False, phase_end_damage_start = 15000),
        Phase("Phase 3", True, phase_end_health=15),
        Phase("Phase 4", True, phase_end_health=1)
    ])
]
BOSSES = {boss.boss_ids[0]: boss for boss in BOSS_ARRAY}
