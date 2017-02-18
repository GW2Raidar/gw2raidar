import struct
import re
from enum import Enum, auto

ENCODING = "utf8"

class Activation(Enum):
    NONE = 0
    NORMAL = 1
    QUICKNESS = 2
    CANCEL_FIRE = 3
    CANCEL_CANCEL = 4

class StateChange(Enum):
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
class AgentType(Enum):
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

class CustomSkill(Enum):
    RESURRECT = 1066
    BANDAGE = 1175
    DODGE = 65001

class IFF(Enum):
    FRIEND = 0
    FOE = 1
    UNKNOWN = 2

class Result(Enum):
    NORMAL=0
    CRIT=1
    GLANCE=2
    BLOCK=3
    EVADE=4
    INTERRUPT=5
    ABSORB=6
    BLIND=7
    KILLING_BLOW=8

class Boon(Enum):
    MIGHT = auto()
    QUICKNESS= auto()
    FURY= auto()
    PROTECTION = auto()
    ALACRITY = auto()
    SPOTTER = auto()
    SPIRIT_OF_FROST = auto()
    SUN_SPIRIT = auto()
    GLYPH_OF_EMPOWERMENT = auto()
    GRACE_OF_THE_LAND = auto()
    EMPOWER_ALLIES = auto()
    BANNER_OF_STRENGTH = auto()
    BANNER_OF_DISCIPLINE = auto()
    SOOTHING_MIST = auto()


class FileFormatException(BaseException):
    pass

class Agent:
    def whitelistName(self, name):
        newName = re.sub("[^\w \\.\\-]","?", name)
        if newName != name:
            print("Unexpected name: {0}", name.__repr__())
        return newName

    def __init__(self, data):
        self.addr, prof, elite, self.toughness, self.healing, self.condition, name_account = struct.unpack("<Qlllll64s4x", data)
        self.prof = AgentType(prof) if prof in map(lambda a:a.value, list(AgentType)) else AgentType.UNKNOWN
        self.elite = elite > 0
        self.name, self.account = name_account.decode(ENCODING).split("\0")[0:2]
        if self.account:
            self.account = self.whitelistName(self.account[1:])
        self.name = self.whitelistName(self.name)

    def __str__(self):
        return "{0} ({1}) - {2} (elite: {3}) - id {4}".format(self.name, self.account, self.prof, self.elite, self.addr)

class Skill:
    def __init__(self, data):
        self.id, name = struct.unpack("<l64s", data)
        self.name = name.decode(ENCODING)

class Event:
    def __init__(self, data):
        self.time, self.src_agent, self.dst_agent, self.value, self.buff_dmg, self.overstack_value, self.skillid, self.src_instid, self.dst_instid, self.src_master_instid, self.iss_offset, self.iss_offset_target, self.iss_bd_offset, self.iss_bd_offset_target, self.iss_alt_offset, self.iss_alt_offset_target, self.skar, self.skar_alt, self.skar_use_alt, self.iff, self.buff, self.result, self.is_activation, self.is_buffremove, self.is_ninety, self.is_fifty, self.is_moving, self.is_statechange, self.is_flanking, self.result_local, self.ident_local = struct.unpack("<QQQllHHHHHBBBBBBBBBBBBBBBBBBBBBx", data)

class Encounter:
    def __init__(self, file):
        evtc, self.version, self.area_id, _ = struct.unpack("<4s9sHc", file.read(16))
        if evtc != b"EVTC":
            raise FileFormatException("Not an EVTC file")

        num_agents, = struct.unpack("<i", file.read(4))
        self.agents = [Agent(file.read(96)) for _ in range(num_agents)]

        num_skills, = struct.unpack("<i", file.read(4))
        self.skills = [Skill(file.read(68)) for _ in range(num_skills)]

        self.events = []
        while True:
            data = file.read(64)
            if not data: break
            self.events.append(Event(data))



