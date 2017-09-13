__author__ = "Toeofdoom"

import time
import sys
import os.path
from evtcparser import *
from analyser import *
from enum import IntEnum
import json
from zipfile import ZipFile

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

def format_value(value):
    if isinstance(value, IntEnum):
        return value.name
    else:
        return value

def print_node(key, node, f=None):
    basic_values = list(filter(lambda key:is_basic_value(key[1]), node.items()))
    if basic_values:
        output_string = "{0}: {1}".format(key, ", ".join(
            ["{0}:{1}".format(name, format_value(value)) for name,value in basic_values]))
        print(output_string, file=f)

def main():
    filename = sys.argv[1]

    print("Parsing {0}".format(filename))

    zipfile = None

    filenames = sys.argv[1].split(",")
    start_all = time.clock()
    for filename in filenames:
        print("Loading {0}".format(filename))
        with open(filename, mode='rb') as file:

            if filename.endswith('.evtc.zip'):
                zipfile = ZipFile(file)
                contents = zipfile.infolist()
                if len(contents) == 1:
                    file = zipfile.open(contents[0].filename)
                else:
                    print('Only single-file ZIP archives are allowed', file=sys.stderr)
                    sys.exit(1)

            start = time.clock()
            e = parser.Encounter(file)
            print("Parsing took {0} seconds".format(time.clock() - start))
            print("Evtc version {0}".format(e.version))

            start = time.clock()
            a = analyser.Analyser(e)
            print("Analyser took {0} seconds".format(time.clock() - start))

            start = time.clock()
            with open('Output/'+os.path.basename(filename)+'.txt','w') as output_file:
                flattened = flatten(a.data)
                for key in sorted(flattened.keys()):
                    if "-s" not in sys.argv:
                        print_node(key, flattened[key])
                    print_node(key, flattened[key], output_file)
            print("Completed parsing {0} - Success: {1}".format(
                  list(a.data['Category']['boss']['Boss'].keys())[0],
                  a.data['Category']['encounter']['success']))
            print("Readable dump took {0} seconds".format(time.clock() - start))

            if "--no-json" not in sys.argv:
                start = time.clock()
                print(json.dumps(a.data), file=open('output.json','w'))
                print("JSon dump took {0} seconds".format(time.clock() - start))
    print("Analysing all took {0} seconds".format(time.clock() - start_all))

if __name__ == "__main__":
    main()
