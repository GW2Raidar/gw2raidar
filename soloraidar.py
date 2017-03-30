__author__ = "Toeofdoom"

import time
import sys
from evtcparser import *
from analyser import *
import json

def is_basic_value(node):
    try:
        dict(node)
        return False
    except:
        return True

def flatten(root):
    nodes = dict((key, dict(node)) for key,node in root.items())
    stack = list(nodes.keys())
    for node_name in stack:
        node = nodes[node_name]
        for child_name, child in node.items():
            try:
                full_child_name = "{0}-{1}".format(node_name, child_name)
                nodes[full_child_name] = dict(child)
                stack.append(full_child_name)
            except TypeError:
                pass
            except ValueError:
                pass
    return nodes

def print_node(key, node, f):
    basic_values = list(filter(lambda key:is_basic_value(key[1]), node.items()))
    if basic_values:
        output_string = "{0}: {1}".format(key, ", ".join(
            ["{0}:{1}".format(name, value) for name,value in basic_values]))
        print(output_string, file=f)
        print(output_string)

def main():
    filename = sys.argv[1]

    print("Parsing {0}".format(filename))
    with open(sys.argv[1], mode='rb') as file:
        start = time.clock()
        e = parser.Encounter(file)
        print("Parsing took {0} seconds".format(time.clock() - start))

        start = time.clock()
        a = analyser.Analyser(e)
        print("Analyser took {0} seconds".format(time.clock() - start))

        if "-s" not in sys.argv:
            start = time.clock()
            print()

            print("Collector-based-data:")

            with open('output.txt','w') as output_file:
                flattened = flatten(a.data)
                for key in sorted(flattened.keys()):
                    print_node(key, flattened[key], output_file)
            print("Readable dump took {0} seconds".format(time.clock() - start))

        if "--no-json" not in sys.argv:
            start = time.clock()
            print(json.dumps(a.data), file=open('output.json','w'))
            print("JSon dump took {0} seconds".format(time.clock() - start))

if __name__ == "__main__":
    main()
