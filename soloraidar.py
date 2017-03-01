__author__ = "Toeofdoom"

import sys
from evtcparser import *
from analyser import *

def is_basic_value(node):
    try:
        dict(node)
        return False
    except:
        return True

def flatten(root):
    nodes = dict((key, dict(node)) for key,node in root)
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
    return nodes

def print_node(key, node):
    basic_values = filter(lambda key:is_basic_value(key[1]), node.items())
    print("{0}: {1}".format(key, ", ".join(
        ["{0}:{1}".format(name, value) for name,value in basic_values])))

def main():
    filename = sys.argv[1]

    print("Parsing {0}".format(filename))
    with open(sys.argv[1], mode='rb') as file:
        e = parser.Encounter(file)
        a = analyser.Analyser(e)
        print(a.players)
        print(a.total)
        print(a.info)

if __name__ == "__main__":
    main()
