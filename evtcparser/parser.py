__author__ = 'Owner'


import struct

ENCODING = "utf8"

class FileFormatException(BaseException):
    pass

class Agent:
    def __init__(self, data):
        self.addr, prof, elite, self.toughness, self.healing, self.condition, name_account = struct.unpack("<QLLlll64s4x", data)
        self.prof = prof
        self.elite = elite != 0
        self.name, self.account = name_account.decode(ENCODING).split("\0")[0:2]
        if self.account:
            self.account = self.account[1:]

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



