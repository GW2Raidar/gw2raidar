import re
from enum import IntEnum
import struct
import numpy as np
import pandas as pd

ENCODING = "utf8"

class Activation(IntEnum):
    NONE = 0
    NORMAL = 1
    QUICKNESS = 2
    CANCEL_FIRE = 3
    CANCEL_CANCEL = 4

class StateChange(IntEnum):
    NORMAL = 0
    ENTER_COMBAT = 1
    EXIT_COMBAT = 2
    CHANGE_UP = 3
    CHANGE_DEAD = 4
    CHANGE_DOWN = 5
    SPAWN = 6
    DESPAWN = 7
    HEALTH_UPDATE = 8
    LOG_START = 9
    LOG_END = 10

#Change to another data type - it's not really an enum?
class AgentType(IntEnum):
    NO_ID = -1
    UNKNOWN = 0
    GUARDIAN = 1
    WARRIOR = 2
    ENGINEER = 3
    RANGER = 4
    THIEF = 5
    ELEMENTALIST = 6
    MESMER = 7
    NECROMANCER = 8
    REVENANT = 9
    MURSAAT_OVERSEER = 17172

    def is_player(self):
        return AgentType.GUARDIAN.value <= self.value <= AgentType.REVENANT.value


class CustomSkill(IntEnum):
    RESURRECT = 1066
    BANDAGE = 1175
    DODGE = 65001

class IFF(IntEnum):
    FRIEND = 0
    FOE = 1
    UNKNOWN = 2

class Result(IntEnum):
    NORMAL=0
    CRIT=1
    GLANCE=2
    BLOCK=3
    EVADE=4
    INTERRUPT=5
    ABSORB=6
    BLIND=7
    KILLING_BLOW=8

class Boon(IntEnum):
    MIGHT = 1
    QUICKNESS = 2
    FURY = 3
    PROTECTION = 4
    ALACRITY = 5
    SPOTTER = 6
    SPIRIT_OF_FROST = 7
    SUN_SPIRIT = 8
    GLYPH_OF_EMPOWERMENT = 9
    GRACE_OF_THE_LAND = 10
    EMPOWER_ALLIES = 11
    BANNER_OF_STRENGTH = 12
    BANNER_OF_DISCIPLINE = 13
    SOOTHING_MIST = 14


class FileFormatException(BaseException):
    pass

class Agent:
    def whitelistName(self, name):
        new_name = re.sub("[^\w \\.\\-]","?", name)
        if new_name != name:
            print("Unexpected name: {0}", name.__repr__())
        return new_name

    def __init__(self, data):
        self.addr, prof, elite, self.toughness, self.healing, self.condition, name_account = struct.unpack("<Qlllll64s4x", data)
        self.prof = AgentType(prof) if prof in map(lambda a:a.value, list(AgentType)) else AgentType.UNKNOWN
        self.elite = elite > 0
        self.name, self.account = name_account.decode(ENCODING).split("\0")[0:2]
        if self.account:
            self.account = self.whitelistName(self.account[1:])
        self.name = self.whitelistName(self.name)

        self.inst_id = None

    def __str__(self):
        return "{0} ({1}) - {2} (elite: {3}) - id {4}".format(self.name, self.account, self.prof, self.elite, self.addr)

    def set_inst_id(self, id):
        if id == 0:
            return
        if self.inst_id is None:
            self.inst_id = id
        else:
            if self.inst_id != id:
                raise Exception("Multiples ids for agent {0}: {1},{2}", self.name, self.inst_id, id)

class Skill:
    def __init__(self, data):
        self.id, name = struct.unpack("<l64s", data)
        self.name = name.decode(ENCODING).rstrip('\0')

AGENT_DTYPE = np.dtype([
        ('addr', np.uint64),
        ('prof', np.int32),
        ('elite', np.int32),
        ('toughness', np.int32),
        ('healing', np.int32),
        ('condition', np.int32),
        ('name', '|S64'),
    ], True)

SKILL_DTYPE = np.dtype([
        ('id', np.int32),
        ('name', 'S64'),
    ], True)

EVENT_DTYPE = np.dtype([
        ('time', np.uint64),
        ('src_agent', np.uint64),
        ('dst_agent', np.uint64),
        ('value', np.int32),
        ('buff_dmg', np.int32),
        ('overstack_value', np.uint16),
        ('skillid', np.uint16),
        ('src_instid', np.uint16),
        ('dst_instid', np.uint16),
        ('src_master_instid', np.uint16),
        ('iss_offset', np.uint8),
        ('iss_offset_target', np.uint8),
        ('iss_bd_offset', np.uint8),
        ('iss_bd_offset_target', np.uint8),
        ('iss_alt_offset', np.uint8),
        ('iss_alt_offset_target', np.uint8),
        ('skar', np.uint8),
        ('skar_aly', np.uint8),
        ('skar_use_alt', np.uint8),
        ('iff', np.uint8),
        ('buff', np.uint8),
        ('result', np.uint8),
        ('is_activation', np.uint8),
        ('is_buffremove', np.uint8),
        ('is_ninety', np.uint8),
        ('is_fifty', np.uint8),
        ('is_moving', np.uint8),
        ('state_change', np.uint8),
        ('is_flanking', np.uint8),
        ('result_local', np.uint8),
        ('ident_local', np.uint8),
    ], True)

class Encounter:
    def __init__(self, file):
        evtc, version, self.area_id = struct.unpack("<4s9sHx", file.read(16))
        if evtc != b"EVTC":
            raise FileFormatException("Not an EVTC file")
        self.version = version.decode(ENCODING).rstrip('\0')

        num_agents, = struct.unpack("<i", file.read(4))
        self.agents = pd.DataFrame(np.fromfile(file, dtype=AGENT_DTYPE, count=num_agents))
        split = self.agents.name.str.split(b'\x00', expand=True)
        self.agents['name'] = split[0].str.decode(ENCODING)
        self.agents['account'] = split[1].str.decode(ENCODING)
        self.agents['party'] = split[2].fillna(0).astype(np.uint8)

        num_skills, = struct.unpack("<i", file.read(4))
        self.skills = pd.DataFrame(np.fromfile(file, dtype=SKILL_DTYPE, count=num_skills))
        self.skills['name'] = self.skills['name'].str.decode(ENCODING)

        self.events = pd.DataFrame(np.fromfile(file, dtype=EVENT_DTYPE))

        self.started_at = self.events[self.events.state_change == StateChange.LOG_START]['value'].iloc[0]
        self.ended_at = self.events[self.events.state_change == StateChange.LOG_END]['value'].iloc[-1]

        src_agent_map = self.events[['src_agent', 'src_instid']].rename(columns={ 'src_agent': 'addr', 'src_instid': 'inst_id'})
        dst_agent_map = self.events[['dst_agent', 'dst_instid']].rename(columns={ 'dst_agent': 'addr', 'dst_instid': 'inst_id'})
        agent_map = pd.concat([src_agent_map, dst_agent_map]).drop_duplicates().set_index('addr')
        self.agents = self.agents.set_index('addr').join(agent_map)


def main():
    with open('/Users/amadan/Downloads/20170222/20170222-204228.evtc', 'rb') as file:
        return Encounter(file)

main()
