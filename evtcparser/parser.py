import re
from enum import IntEnum
import struct
import numpy as np
import pandas as pd
from io import UnsupportedOperation

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
    WEAPON_SWAP = 11
    MAX_HEALTH_UPDATE = 12
    POINT_OF_VIEW = 13
    LANGUAGE = 14
    GW_BUILD = 15
    SHARD_ID = 16
    REWARD = 17

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

    def is_player(self):
        return AgentType.GUARDIAN <= self <= AgentType.REVENANT


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
    STRENGTH_IN_NUMBERS=15


class EvtcParseException(BaseException):
    pass


AGENT_LEGACY_DTYPE = np.dtype([
        ('addr', np.int64), # required: https://github.com/pandas-dev/pandas/issues/3506
        ('prof', np.int32),
        ('elite', np.int32),
        ('toughness', np.int32),
        ('healing', np.int32),
        ('condition', np.int32),
        ('name', '|S64'),
    ], True)

AGENT_20180724_DTYPE = np.dtype([
    ('addr', np.int64), # required: https://github.com/pandas-dev/pandas/issues/3506
    ('prof', np.uint32),
    ('elite', np.int32),
    ('toughness', np.int16),
    ('concentration',np.int16),
    ('healing', np.int16),
    ('pad1',np.int16),
    ('condition', np.int16),
    ('pad2',np.int16),
    ('name', '|S64'),
], True)

SKILL_DTYPE = np.dtype([
        ('id', np.int32),
        ('name', 'S64'),
    ], True)

EVENT_LEGACY_DTYPE = np.dtype([
        ('time', np.uint64),
        ('src_agent', np.int64),
        ('dst_agent', np.int64),
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
        ('is_shields', np.uint8),
        ('result_local', np.uint8),
        ('ident_local', np.uint8),
    ], True)

EVENT_DTYPE = np.dtype([
        ('time', np.uint64),
        ('src_agent', np.int64),
        ('dst_agent', np.int64),
        ('value', np.int32),
        ('buff_dmg', np.int32),
        ('overstack_value', np.uint32),
        ('skillid', np.uint32),
        ('src_instid', np.uint16),
        ('dst_instid', np.uint16),
        ('src_master_instid', np.uint16),
        ('dst_master_instid', np.uint16),
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
        ('is_shields', np.uint8),
        ('is_offcycle', np.uint8),
        ('pad61', np.uint8),
        ('pad62', np.uint8),
        ('pad63', np.uint8),
        ('pad64', np.uint8),
    ], True)

class Encounter:
    def _read_header(self, file):
        if len(file.peek(16)) < 16:
            raise EvtcParseException("Not an EVTC file")
        evtc, version, self.area_id, self.revision = struct.unpack("<4s9sHB", file.read(16))
        if evtc != b"EVTC":
            raise EvtcParseException("Not an EVTC file")
        self.version = version.decode(ENCODING).rstrip('\0')

    def _read_agents(self, file):
        dtype = AGENT_20180724_DTYPE
        num_agents, = struct.unpack("<i", file.read(4))
        agents_string = file.read(dtype.itemsize * num_agents)
        
        self.agents = pd.DataFrame(np.fromstring(agents_string, dtype=dtype, count=num_agents))
        split = self.agents.name.str.split(b'\x00:?', expand=True)
        if len(split.columns) > 1:
            self.agents['name'] = split[0].str.decode(ENCODING)
            self.agents['account'] = split[1].str.decode(ENCODING)
            self.agents['party'] = split[2].fillna(0).astype(np.uint8)
        else:
            self.agents['account'] = None
            self.agents['party'] = 0
            
        self.agents[['prof']] = self.agents[['prof']].astype(np.uint32)

    def _read_skills(self, file):
        num_skills, = struct.unpack("<i", file.read(4))
        skills_string = file.read(SKILL_DTYPE.itemsize * num_skills)
        self.skills = pd.DataFrame(np.fromstring(skills_string, dtype=SKILL_DTYPE, count=num_skills)).set_index('id')
        self.skills['name'] = self.skills['name'].str.decode(ENCODING)
    
    def _read_events(self, file):
        events_string = file.read()
        if(self.version < "20181002" and self.revision == 0):
            self.events = pd.DataFrame(np.fromstring(events_string, dtype=EVENT_LEGACY_DTYPE))
            for name in ['iss_offset','iss_offset_target','iss_bd_offset',
                    'iss_bd_offset_target','iss_alt_offset','iss_alt_offset_target',
                    'result_local','ident_local']:
                del self.events[name]
                self.events['dst_master_instid'] = 0
        else:
            self.events = pd.DataFrame(np.fromstring(events_string, dtype=EVENT_DTYPE))

        if len(self.events[self.events.state_change == StateChange.LOG_END]) == 0:
            pass
            # raise EvtcParseException('EVTC missing end event')
        else:
            self.log_ended_at = self.events[self.events.state_change == StateChange.LOG_END]['value'].iloc[-1]

        log_start_events = self.events[self.events.state_change == StateChange.LOG_START]['value']
        if len(log_start_events) == 0:
            raise EvtcParseException('EVTC missing start event')
        else:
            self.log_started_at = log_start_events.iloc[0]

    def _old_add_inst_id_to_agents(self):
        
        self.raw_agents = self.agents
        src_agent_map = self.events[['src_agent', 'src_instid']].rename(columns={ 'src_agent': 'addr', 'src_instid': 'inst_id'})
        dst_agent_map = self.events[['dst_agent', 'dst_instid']].rename(columns={ 'dst_agent': 'addr', 'dst_instid': 'inst_id'})
        agent_map = pd.concat([src_agent_map, dst_agent_map])
        agent_map = agent_map[agent_map.inst_id != 0].drop_duplicates().set_index('addr')
        self.agents = self.agents.set_index('addr').join(agent_map).groupby('inst_id').first()
        
    def _add_inst_id_to_agents(self):   
        #ignore higher order state change events because they can have junk values
        agent_events = self.events[self.events.state_change <= 8]

        src_agent_map = agent_events[['time', 'src_agent', 'src_instid']].rename(columns={ 'src_agent': 'addr', 'src_instid': 'inst_id'})
        dst_agent_map = agent_events[['time', 'dst_agent', 'dst_instid']].rename(columns={ 'dst_agent': 'addr', 'dst_instid': 'inst_id'})

        agent_map = pd.concat([src_agent_map, dst_agent_map])
        agent_map = agent_map[agent_map.inst_id != 0]
        agent_map = agent_map.sort_values(by='time')
        agent_map.drop_duplicates(subset='addr',inplace=True)
        agent_map.insert(0, 'new_id', range(1, 1 + len(agent_map)))

        del self.events['src_instid']
        del self.events['dst_instid']
        self.events = pd.merge(left=self.events,right=agent_map[['addr', 'new_id']].rename(columns={'addr' : 'src_agent', 'new_id' : 'src_instid'}), how='left', left_on='src_agent', right_on='src_agent')
        self.events = pd.merge(left=self.events,right=agent_map[['addr', 'new_id']].rename(columns={'addr' : 'dst_agent', 'new_id' : 'dst_instid'}), how='left')
        instid_map = agent_map.drop_duplicates(subset='inst_id',inplace=False)
        self.events = self.events.rename(columns={'src_master_instid' : 'old_src_master_instid'})
        self.events = pd.merge(left=self.events,right=instid_map[['inst_id', 'new_id']].rename(columns={'inst_id' : 'old_src_master_instid', 'new_id' : 'src_master_instid'}), how='left') 
        self.events.fillna(0, inplace=True)
        self.events[['src_instid', 'dst_instid','src_master_instid']] = self.events[['src_instid', 'dst_instid','src_master_instid']].astype(np.int64)
        
        #self.addr_agents = self.agents.set_index('addr')
        # deal with duplicate inst_id for different addrs
        self.agents = pd.merge(left=self.agents,right=agent_map[['addr', 'new_id']].rename(columns={'new_id' : 'inst_id'}), how='left')
        self.agents.fillna(-1, inplace=True)
        self.agents[['inst_id']] = self.agents[['inst_id']].astype(np.int64)
        self.agents = self.agents.set_index('inst_id')
        del self.events['old_src_master_instid']
        del self.agents['addr']

    def __init__(self, file):
        try:
            self._read_header(file)

            if self.version < "20170419":
                raise EvtcParseException('Unsupported EVTC version')
            self._read_agents(file)
            self._read_skills(file)
            self._read_events(file)
            self._add_inst_id_to_agents()
        except UnsupportedOperation:
            raise EvtcParseException('Bad EVTC file')
        except ValueError:
            raise EvtcParseException('Bad or truncated EVTC file')
