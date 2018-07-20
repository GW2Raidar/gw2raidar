from enum import IntEnum
from evtcparser import *
import pandas as pd
import numpy as np
from analyser.analyser import LogType
from functools import reduce
import json
import ctypes
import struct
import math as math

def convert2f(val):
    class VECTOR2(ctypes.Structure):
        _fields_ = [("x", ctypes.c_float),
                    ("y", ctypes.c_float)]
    vec = VECTOR2()
    long = ctypes.c_ulonglong(val)
    ctypes.memmove(ctypes.addressof(vec),ctypes.addressof(long),8)
    return [vec.x, vec.y]

def convertHeading(val):
    size = np.linalg.norm(val)
    if size < 0.0000001:
        return np.nan
    unit = val / np.linalg.norm(val)
    angle = np.arccos(np.dot([0,1],unit))
    heading = angle
    
    if unit[0] > 0:
        heading = 2 * math.pi - angle
    return heading

def convertf(val):
    class VECTOR1(ctypes.Structure):
        _fields_ = [("z", ctypes.c_float)]
    vec = VECTOR1()
    long = ctypes.c_ulong(val)
    ctypes.memmove(ctypes.addressof(vec),ctypes.addressof(long),4)
    return vec.z

class ReplayWriter:
    
    def __init__(self, encounter, analyser):
        self.players = analyser.players
        self.boss = analyser.boss_info
        self.boss_instids = analyser.boss_instids
        self.agents = encounter.agents
        self.events = encounter.events.copy()
        self.start_time = analyser.start_time
        self.end_time = analyser.end_time
        self.events['time'] = self.events['time'].apply(lambda x : (x - self.start_time) / 1000.0)        
        self.damage_events = self.events[(self.events.state_change == 0)&((self.events.type == LogType.POWER)|(self.events.type == LogType.CONDI))]
        self.damage_events = self.damage_events.assign(damage =
                                         np.where(self.damage_events.type == LogType.POWER,
                                                  self.damage_events['value'],
                                                  self.damage_events['buff_dmg']))
        self.damage_events = self.damage_events[self.damage_events.damage > 0]
        
    
    def writePlayerData(self, agentId, dataOut):
        self.writeAgentData(agentId, dataOut)
        dataOut["base-state"][str(agentId)]["color"] = "#BBDDFF"
        dataOut["base-state"][str(agentId)]["state"] = 'Up'
        
        self.writeBossDamageTrack(agentId, dataOut)
        
        stateChangeEvents = self.events[(self.events.src_instid == agentId) & ((self.events.state_change == 3)|(self.events.state_change == 4)|(self.events.state_change == 5))]
        if len(stateChangeEvents) > 0:
            trackState = {"path" : [str(agentId), "state"], "data-type" : "string", "update-type" : "delta", "data" : []}
            for event in stateChangeEvents[['time', 'state_change']].itertuples():
                state = {3 : 'Up', 4: 'Dead', 5: 'Down'}[event[2]]
                trackState["data"] += [{'time' : event[1], 'value' : state}]
            dataOut["tracks"] += [trackState]
        
    def writeBossData(self, agentId, dataOut):
        self.writeAgentData(agentId, dataOut)
        dataOut["base-state"][str(agentId)]["color"] = "#FF0000"
        
    def writeWallData(self, agentId, dataOut):
        self.writeAgentData(agentId, dataOut)
        dataOut["base-state"][str(agentId)]["color"] = "#FF0000"
    
    def writeAgentData(self, agentId, dataOut):
        agent = self.agents.loc[agentId]
        agentData = {"name" : agent["name"]}
        dataOut["base-state"][str(agentId)] = agentData
                
        self.writePositionTracks(agentId, dataOut)
        
    def writeDirectionTrack(self, agentId, dataOut):
        agent = self.agents.loc[agentId]
        
        trackHeading = {"path" : [str(agentId), "heading"], "data-type" : "numeric", "update-type" : "delta", "interpolation" : "slerp"}
        dataOut["tracks"] += [trackHeading]
        
        dirEvents = self.events[(self.events.src_instid == agentId) & (self.events.state_change == 20)]
        dirEvents = dirEvents.assign(xy=pd.Series(dirEvents['dst_agent'].apply(convert2f)).values)
        dirEvents = dirEvents.assign(heading=pd.Series(dirEvents['xy'].apply(convertHeading)).values)
        dirEvents = dirEvents.dropna()
        
        dataOut["base-state"][str(agentId)]["heading"] = dirEvents.iloc[0]['heading']
        
        trackHeading["data"] = []
        gap = 0.55
        offsetTime = 0.3
        lastTime = dirEvents.iloc[0]['time'] - offsetTime
        lastEvent = None
        for event in dirEvents[['time', 'heading']].itertuples():
            if event.time - lastTime > gap and not lastEvent is None:
                trackHeading["data"] += [{'time' : event[1] - offsetTime, 'value' : lastEvent[2]}]
            trackHeading["data"] += [{'time' : event[1], 'value' : event[2]}]
            lastEvent = event
            lastTime = event[1]
                
    def writePositionTracks(self, agentId, dataOut):
        agent = self.agents.loc[agentId]
        trackx = {"path" : [str(agentId), "position", "x"], "data-type" : "numeric", "update-type" : "delta", "interpolation" : "lerp"}
        tracky = {"path" : [str(agentId), "position", "y"], "data-type" : "numeric", "update-type" : "delta", "interpolation" : "lerp"}
        trackz = {"path" : [str(agentId), "position", "z"], "data-type" : "numeric", "update-type" : "delta", "interpolation" : "lerp"}
        moveEvents = self.events[(self.events.src_instid == agentId) & (self.events.state_change == 19)]
      
        trackx["start-time"] = moveEvents.iloc[0].time
        tracky["start-time"] = moveEvents.iloc[0].time
        trackz["start-time"] = moveEvents.iloc[0].time
        dataOut["tracks"] += [trackx]
        dataOut["tracks"] += [tracky]
        dataOut["tracks"] += [trackz]
        moveEvents = moveEvents.assign(xy=pd.Series(moveEvents['dst_agent'].apply(convert2f)).values)
        moveEvents = moveEvents.assign(x=pd.Series(moveEvents['xy'].apply(lambda x: x[0])).values)
        moveEvents = moveEvents.assign(y=pd.Series(moveEvents['xy'].apply(lambda x: x[1])).values)
        moveEvents = moveEvents.assign(z=pd.Series(moveEvents['value'].apply(convertf)).values)

        trackx["data"] = []
        tracky["data"] = []
        trackz["data"] = []

        dataOut["base-state"][str(agentId)]["position"] = {}
        dataOut["base-state"][str(agentId)]["position"]["x"] = moveEvents.iloc[0]['x']
        dataOut["base-state"][str(agentId)]["position"]["y"] = moveEvents.iloc[0]['y']
        dataOut["base-state"][str(agentId)]["position"]["z"] = moveEvents.iloc[0]['z']
        
        gap = 0.55
        offsetTime = 0.3
        lastTime = moveEvents.iloc[0]['time'] - offsetTime
        lastEvent = None
        for event in moveEvents[['time', 'x', 'y', 'z']].itertuples():
            if event.time - lastTime > gap and not lastEvent is None:
                trackx["data"] += [{'time' : event[1] - offsetTime, 'value' : lastEvent[2]}]
                tracky["data"] += [{'time' : event[1] - offsetTime, 'value' : lastEvent[3]}]
                trackz["data"] += [{'time' : event[1] - offsetTime, 'value' : lastEvent[4]}]
            trackx["data"] += [{'time' : event[1], 'value' : event[2]}]
            tracky["data"] += [{'time' : event[1], 'value' : event[3]}]
            trackz["data"] += [{'time' : event[1], 'value' : event[4]}]
            lastEvent = event
            lastTime = event[1]
            
    def writeBossDamageTrack(self, agentId, dataOut):
        agent = self.agents.loc[agentId]
        
        trackDamage = {"path" : [str(agentId), "bossdamage"], "data-type" : "numeric", "update-type" : "delta", "interpolation" : "floor"}
                
        events = self.damage_events[(self.damage_events.ult_src_instid == agentId) & (self.damage_events.damage > 0) & (self.damage_events.iff == 1) & (self.damage_events.dst_instid.isin(self.boss_instids))]
        events['bossdamagesum'] = events.value.cumsum() + events.buff_dmg.cumsum()
        
        if len(events) > 0:
            dataOut["base-state"][str(agentId)]["bossdamage"] = 0
            dataOut["tracks"] += [trackDamage]

            trackDamage["data"] = []
            for event in events[['time', 'bossdamagesum']].itertuples():
                trackDamage["data"] += [{'time' : event[1], 'value' : int(event[2])}]
        
    def generateReplay(self):
        data = {"info" : {}, "base-state" : {}, "tracks" : []}
        data["info"]["encounter"] = self.boss.name
        data["info"]["duration"] = (self.end_time - self.start_time) / 1000.0
        for actorId in (list(self.players.index)):
            self.writePlayerData(actorId, data)   
        for actorId in (list(self.boss_instids)):
            self.writeBossData(actorId, data)     
        #for actorId in (list(self.agents[self.agents.prof == 19474].index.values)):
        #    self.writeWallData(actorId, data)

        return json.dumps(data)