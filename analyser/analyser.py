
class Metric:
    def __init__(self, name, version, value, data):
        self.name = name
        self.version = version
        self.value =value
        self.data = data

    def __str__(self):
        return "{0}, version {1}: {2} ({3})".format(self.name, self.version, self.value, self.data)

def ComputeAllMetrics(encounter):
    targetAgent = encounter.agents[0]

    agentNameMap = {}
    for agent in encounter.agents:
        agentNameMap[agent.addr] = agent.name

    startTime = encounter.events[0].time
    endTime = encounter.events[-1].time
    time = (endTime - startTime)/1000
    condi = 0
    power = 0
    playerdps = {}
    for event in filter(lambda a: a.dst_agent == targetAgent.addr, encounter.events):
        condi += event.buff_dmg
        power += event.value
        if not event.src_agent in playerdps:
            playerdps[event.src_agent] = 0
        playerdps[event.src_agent] += event.buff_dmg

    playerdps2 = {}
    for id in playerdps:
        name = agentNameMap[id]
        playerdps2[name] = playerdps[id]/time

    return [Metric("RanSuccessfully", 1, 1, None),
            Metric("TeamDPS", 1, (condi + power)/time, "condi: {0}, power: {1}, players: {2}"
                   .format(condi/time, power/time, playerdps2)),
            Metric("Time", 1, time, None)]