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
        self.boss_instids = analyser.boss_instids
        self.agents = encounter.agents
        self.events = encounter.events
        self.start_time = analyser.start_time
        
    def generateReplay(self):
        data = {"tracks" : []}
        for playerId in (list(self.players.index) + list(self.boss_instids)):
            player = self.agents.loc[playerId]
            trackx = {"path" : [player["name"], "position", "x"], "data-type" : "numeric", "update-type" : "delta", "interpolation" : "lerp"}
            tracky = {"path" : [player["name"], "position", "y"], "data-type" : "numeric", "update-type" : "delta", "interpolation" : "lerp"}
            trackz = {"path" : [player["name"], "position", "z"], "data-type" : "numeric", "update-type" : "delta", "interpolation" : "lerp"}
            moveEvents = self.events[(self.events.src_instid == playerId) & (self.events.state_change == 19)]
        
            moveEvents['time'] = moveEvents['time'].apply(lambda x : (x - self.start_time) / 1000.0)
            trackx["start-time"] = moveEvents.iloc[0].time
            tracky["start-time"] = moveEvents.iloc[0].time
            trackz["start-time"] = moveEvents.iloc[0].time
            data["tracks"] += [trackx]
            data["tracks"] += [tracky]
            data["tracks"] += [trackz]
            moveEvents = moveEvents.assign(xy=pd.Series(moveEvents['dst_agent'].apply(convert2f)).values)
            moveEvents = moveEvents.assign(x=pd.Series(moveEvents['xy'].apply(lambda x: x[0])).values)
            moveEvents = moveEvents.assign(y=pd.Series(moveEvents['xy'].apply(lambda x: x[1])).values)
            moveEvents = moveEvents.assign(z=pd.Series(moveEvents['value'].apply(convertf)).values)
            
            trackx["data"] = []
            tracky["data"] = []
            trackz["data"] = []
            
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
            
        return json.dumps(data)