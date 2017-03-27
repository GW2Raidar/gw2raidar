
def percentage(n):
    return round(n * 100, 1)

class Collector:
    """ Used for collecting data and automatically structuring it for output. """

    def __init__(self, ordering, registrations, context, all_data, aliases):
        self.ordering = ordering
        self.registrations = registrations
        self.context = context
        self.all_data = all_data
        self.aliases = aliases

    @classmethod
    def root(cls, ordering):
        return cls(ordering, [], {}, {}, {})

    def group(self, function, data, *group_mappings):
        if not group_mappings:
            self.run(function, data)
            return
        group_from,group_to = group_mappings[0]
        remaining_group_mappings = group_mappings[1:]
        groups = data.groupby(group_from)

        alias = self.aliases.get(group_from, {})
        for name, group in groups:
            name = alias.get(name,name)
            self.with_key(group_to, name).group(function, group, *remaining_group_mappings)

    def run(self, function, data):
        function(self, data.copy(True))

    def add_data(self, name, value, type = None):
        if type:
            value = type(value)
        output_block = self.all_data
        #print("Adding {0}:{1} to context {2}".format(name, value, self.context))
        sorted_context = [key for key in self.ordering if key in self.context] + sorted([
            key for key in self.context if key not in self.ordering])

        for path_key in sorted_context:
            output_block = Collector._navigate(output_block, path_key)
            output_block = Collector._navigate(output_block, self.context[path_key])
        output_block[name] = value

    def with_key(self, key, value):
        new_context = dict(self.context)
        new_context[key] = value
        return Collector(self.ordering, self.registrations, new_context, self.all_data, self.aliases)

    def alias(self, key, alias_map):
        self.aliases[key] = alias_map

    @staticmethod
    def _navigate(dictionary, key):
        if key not in dictionary:
            new_node = {}
            dictionary[key] = new_node
            return new_node
        return dictionary[key]
