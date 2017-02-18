__author__ = "Toeofdoom"

import sys
from evtcparser import *
from analyser import *

def main():
    filename = sys.argv[1]

    print("Parsing {0}".format(filename))
    with open(sys.argv[1], mode='rb') as file:
        e = parser.Encounter(file)
        metrics = analyser.ComputeAllMetrics(e)
        for agent in filter(lambda a: a.prof != parser.AgentType.NO_ID, e.agents):
            print(agent)
        for metric in metrics:
            print(metric)
        #for skill in e.skills:
        #    print("Skill \"{0}\"".format(skill.name))
        #for event in e.events:
            #print("Skill \"{0}\"".format(event.src_agent))

if __name__ == "__main__":
    main()