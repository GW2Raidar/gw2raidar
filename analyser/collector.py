

class Filter:
    def __init__(self, conversion_function, context_function):
        self.conversion_function = conversion_function
        self.context_function = context_function

    def apply(self, value, context):
        with_context = self.context_function(value, context)
        if not self.conversion_function:
            return with_context
        return self.conversion_function(with_context)

def percentage(n):
    return round(n * 100, 1)

def portion_of(f, name):
    return Filter(f, lambda value,context: 0
                                        if float(context[name]) < 0.001
                                        else float(value)/float(context[name]))

def percentage_of(name):
    return portion_of(percentage, name)

def mapped_to(name):
    return Filter(None, lambda value,context: context.get(name).get(value))

#NOTE: May want to add "range" style data to context levels, such as time or total damage?
class Collector:
    """ Used for collecting data and automatically structuring it for output. """

    def __init__(self, ordering, registrations, context, all_data, context_values):
        self.ordering = ordering
        self.registrations = registrations
        self.context = context
        self.all_data = all_data
        self.context_values = context_values

    @classmethod
    def root(cls, ordering):
        return cls(ordering, [], {}, {}, {})

    def group(self, function, data, *group_mappings):
        if not group_mappings:
            self.run(function, data)
            return
        group_mapping = list(group_mappings[0])
        group_from,group_to = group_mapping[0:2]
        group_filters = group_mapping[2:]
        remaining_group_mappings = group_mappings[1:]
        groups = data.groupby(group_from)

        for name, group in groups:
            for filter in group_filters:
                name = filter.apply(name, self.context_values)
            self.with_key(group_to, name).group(function, group, *remaining_group_mappings)

    def run(self, function, data):
        function(self, data.copy(True))

    def add_data(self, name, value, type = None):
        if type:
            try:
                value = type(value)
            except:
                value = type.apply(value, self.context_values)

        output_block = self.all_data
        sorted_context = [key for key in self.ordering if key in self.context] + sorted([
            key for key in self.context if key not in self.ordering])

        for path_key in sorted_context:
            output_block = Collector._navigate(output_block, path_key)
            output_block = Collector._navigate(output_block, self.context[path_key])
        if name in output_block:
            print("Clash for {0}:{1}".format(self.context, name))
        output_block[name] = value

    def with_key(self, key, value):
        new_context = dict(self.context)
        new_context[key] = value
        return Collector(self.ordering,
                         self.registrations,
                         new_context,
                         self.all_data,
                         dict(self.context_values))

    def set_context_value(self, key, value):
        self.context_values[key] = value

    @staticmethod
    def _navigate(dictionary, key):
        if key not in dictionary:
            new_node = {}
            dictionary[key] = new_node
            return new_node
        return dictionary[key]
