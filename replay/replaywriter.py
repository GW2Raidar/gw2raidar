from enum import IntEnum
from evtcparser import *
import pandas as pd
import numpy as np
import analyser as ana
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
    val[1] *= -1
    size = np.linalg.norm(val)
    if size < 0.0000001:
        return np.nan
    unit = val / np.linalg.norm(val)
    angle = np.arccos(np.dot([0,1],unit))
    heading = angle
    
    if unit[0] < 0:
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
        self.damage_events = self.events[(self.events.state_change == 0)&((self.events.type == ana.analyser.LogType.POWER)|(self.events.type == ana.analyser.LogType.CONDI))]
        self.damage_events = self.damage_events.assign(damage =
                                         np.where(self.damage_events.type == ana.analyser.LogType.POWER,
                                                  self.damage_events['value'],
                                                  self.damage_events['buff_dmg']))
        self.damage_events = self.damage_events[self.damage_events.damage > 0]
        self.buff_data = analyser.buff_data.copy()
        self.buff_data['time'] = self.buff_data['time'].apply(lambda x : (x - self.start_time) / 1000.0)
        
    
    def writePlayerData(self, agentId, dataOut):
        self.writeAgentData(agentId, dataOut)
        agent = self.agents.loc[agentId]
        dataOut["base-state"][str(agentId)]["color"] = "#BBDDFF"
        dataOut["base-state"][str(agentId)]["state"] = 'Up'
        dataOut["base-state"][str(agentId)]["type"] = "Player"
        elite = 0
        if agent.elite == 0:
            elite = 0
        elif agent.elite < 55:
            elite = 1
        else:
            elite = 2
        dataOut["base-state"][str(agentId)]["class"] = ana.analyser.SPECIALISATIONS[ana.analyser.Profession(agent.prof), elite]
            
        
        self.writeBossDamageTrack(agentId, dataOut)
        self.writeCleaveDamageTrack(agentId, dataOut)
        self.writeBuffTracks(agentId, dataOut)
        
        stateChangeEvents = self.events[(self.events.src_instid == agentId) & ((self.events.state_change == 3)|(self.events.state_change == 4)|(self.events.state_change == 5))]
        if len(stateChangeEvents) > 0:
            trackState = {"path" : [str(agentId), "state"], "data-type" : "string", "update-type" : "delta", "data" : []}
            for event in stateChangeEvents[['time', 'state_change']].itertuples():
                state = {3 : 'Up', 4: 'Dead', 5: 'Down'}[event[2]]
                trackState["data"] += [{'time' : event[1], 'value' : state}]
            dataOut["tracks"] += [trackState]
        
    def writeBossData(self, agentId, dataOut):
        self.writeAgentData(agentId, dataOut)
        self.writeHealthUpdates(agentId, dataOut)
        dataOut["base-state"][str(agentId)]["color"] = "#FF0000"
        dataOut["base-state"][str(agentId)]["type"] = "Boss"
        
    def writeWallData(self, agentId, dataOut):
        self.writeAgentData(agentId, dataOut)
        dataOut["base-state"][str(agentId)]["color"] = "#FF0000"
        dataOut["base-state"][str(agentId)]["type"] = "EnemyEffect"
    
    def writeAgentData(self, agentId, dataOut):
        agent = self.agents.loc[agentId]
        agentData = {"name" : agent["name"]}
        dataOut["base-state"][str(agentId)] = agentData
                
        self.writePositionTracks(agentId, dataOut)
        self.writeDirectionTrack(agentId, dataOut)
        
    def writeBuffTracks(self, agentId, dataOut):
        dataOut["base-state"][str(agentId)]["buff"] = {}
        for buffType in ana.buffs.BUFF_TYPES:
            buffData = self.buff_data[(self.buff_data.dst_instid == agentId)&(self.buff_data.buff == buffType.code)]
            if len(buffData) > 0:
                dataOut["base-state"][str(agentId)]["buff"][buffType.code] = 0
                track = {"path" : [str(agentId), "buff", buffType.code], "data-type" : "numeric", "update-type" : "delta", "interpolation" : "floor"}
                track["data"] = []
                dataOut["tracks"] += [track]
                
                lastTotal = 0
                srcStacks = {}
                for event in buffData[['time', 'stacks', 'src_instid']].itertuples():
                    srcStacks[event[3]] = int(event[2])
                    
                    total = sum(srcStacks.values())
                    if total != lastTotal:
                        lastTotal = total
                        track["data"] += [{'time' : event[1], 'value' : total}]                    
                        
    def writeHealthUpdates(self, agentId, dataOut):
        agent = self.agents.loc[agentId]
        
        healthEvents = self.events[(self.events.src_instid == agentId) & (self.events.state_change == 8)]
        
        if len(healthEvents) > 1:
            dataOut["base-state"][str(agentId)]["health"] = 100
            trackHealth = {"path" : [str(agentId), "health"], "data-type" : "numeric", "update-type" : "delta", "interpolation" : "lerp"}
            trackHealth["data"] = []
            dataOut["tracks"] += [trackHealth]
            gap = 5
            lastTime = 0
            lastValue = 100.0
            for event in healthEvents[['time', 'dst_agent']].itertuples():
                if event[1] - lastTime > gap:
                    trackHealth["data"] += [{'time': event[1] - 1.5, 'value': lastValue}]
                trackHealth["data"] += [{'time' : event[1], 'value' : event[2]/100.0}]
                lastTime = event[1]
                lastValue = event[2] / 100.0
        
    def writeDirectionTrack(self, agentId, dataOut):
        agent = self.agents.loc[agentId]
        
        trackHeading = {"path" : [str(agentId), "heading"], "data-type" : "numeric", "update-type" : "delta", "interpolation" : "slerp"}
                
        dirEvents = self.events[(self.events.src_instid == agentId) & (self.events.state_change == 21)]
        dirEvents = dirEvents.assign(xy=pd.Series(dirEvents['dst_agent'].apply(convert2f)).values)
        dirEvents = dirEvents.assign(heading=pd.Series(dirEvents['xy'].apply(convertHeading)).values)
        dirEvents = dirEvents.dropna()
        
        if len(dirEvents) > 0:
            dataOut["base-state"][str(agentId)]["heading"] = dirEvents.iloc[0]['heading']
            dataOut["tracks"] += [trackHeading]

            trackHeading["data"] = []
            gap = 0.8
            offsetTime = 0.5
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
        
        moveEvents = moveEvents.assign(xy=pd.Series(moveEvents['dst_agent'].apply(convert2f)).values)
        moveEvents = moveEvents.assign(x=pd.Series(moveEvents['xy'].apply(lambda x: x[0])).values)
        moveEvents = moveEvents.assign(y=pd.Series(moveEvents['xy'].apply(lambda x: x[1])).values)
        moveEvents = moveEvents.assign(z=pd.Series(moveEvents['value'].apply(convertf)).values)

        trackx["data"] = []
        tracky["data"] = []
        trackz["data"] = []

        if len(moveEvents) > 0:
            trackx["start-time"] = moveEvents.iloc[0].time
            tracky["start-time"] = moveEvents.iloc[0].time
            trackz["start-time"] = moveEvents.iloc[0].time
            dataOut["tracks"] += [trackx]
            dataOut["tracks"] += [tracky]
            dataOut["tracks"] += [trackz]
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
                if not lastEvent is None and abs(event[4] - lastEvent[4]) > 700:
                    trackx["data"] += [{'time' : event[1] - 0.001, 'value' : lastEvent[2]}]
                    tracky["data"] += [{'time' : event[1] - 0.001, 'value' : lastEvent[3]}]
                    trackz["data"] += [{'time' : event[1] - 0.001, 'value' : lastEvent[4]}]
                trackx["data"] += [{'time' : event[1], 'value' : event[2]}]
                tracky["data"] += [{'time' : event[1], 'value' : event[3]}]
                trackz["data"] += [{'time' : event[1], 'value' : event[4]}]
                lastEvent = event
                lastTime = event[1]
            
    def writeBossDamageTrack(self, agentId, dataOut):
        agent = self.agents.loc[agentId]
        trackDamage = {"path" : [str(agentId), "bossdamage"], "data-type" : "numeric", "update-type" : "delta", "interpolation" : "lerp"}
        events = self.damage_events[(self.damage_events.ult_src_instid == agentId) & (self.damage_events.damage > 0) & (self.damage_events.iff == 1) & (self.damage_events.dst_instid.isin(self.boss_instids))]
        events['bossdamagesum'] = events.value.cumsum() + events.buff_dmg.cumsum()
        
        if len(events) > 0:
            dataOut["base-state"][str(agentId)]["bossdamage"] = 0
            dataOut["tracks"] += [trackDamage]
            trackDamage["data"] = []
            for event in events[['time', 'bossdamagesum']].itertuples():
                trackDamage["data"] += [{'time' : event[1], 'value' : int(event[2])}]
                
    def writeCleaveDamageTrack(self, agentId, dataOut):
        agent = self.agents.loc[agentId]
        trackDamage = {"path" : [str(agentId), "cleavedamage"], "data-type" : "numeric", "update-type" : "delta", "interpolation" : "floor"}
        events = self.damage_events[(self.damage_events.ult_src_instid == agentId) & (self.damage_events.damage > 0) & (self.damage_events.iff == 1)]
        events['damagesum'] = events.value.cumsum() + events.buff_dmg.cumsum()
        
        if len(events) > 0:
            dataOut["base-state"][str(agentId)]["cleavedamage"] = 0
            dataOut["tracks"] += [trackDamage]
            trackDamage["data"] = []
            for event in events[['time', 'damagesum']].itertuples():
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