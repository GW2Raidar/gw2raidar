from enum import IntEnum
from evtcparser import *
import pandas as pd
import numpy as np
from functools import reduce
import json
import ctypes
import struct

def convert2f(val):
    class VECTOR2(ctypes.Structure):
        _fields_ = [("x", ctypes.c_float),
                    ("y", ctypes.c_float)]
    vec = VECTOR2()
    long = ctypes.c_ulonglong(val)
    ctypes.memmove(ctypes.addressof(vec),ctypes.addressof(long),8)
    return [vec.x, vec.y]

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
    
    def writePlayerData(self, agentId, dataOut):
        self.writeAgentData(agentId, dataOut)
        dataOut["base-state"][str(agentId)]["color"] = "#BBDDFF"
        dataOut["base-state"][str(agentId)]["state"] = 'Up'
        
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