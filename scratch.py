import timeit
import numpy
import pandas

pandas.set_option("display.max_columns", 12)
pandas.set_option("display.width", 160)

VALUES = ["arch", "prof", "elite", "might", "fury", "quickness", "alacrity", "swiftness", "vigor", "regeneration", "protection", "dps", "cleave", "received", "shielded", "crit", "flanking", "scholar", "seaweed"]
quantiles = numpy.arange(0, 1, 0.01)

frame = pandas.DataFrame(data=numpy.random.rand(100000, len(VALUES)), columns=VALUES)
frame["arch"] = frame["arch"].apply(numpy.digitize, args=[[0.2, 0.4, 1.0]])
frame["prof"] = frame["prof"].apply(numpy.digitize, args=[[0.1, 0.2, 0.3, 0.4, 0.6, 0.7, 0.8, 0.9, 1.0]])
frame["elite"] = frame["elite"].apply(numpy.digitize, args=[[0.1, 0.4, 1.0]])
frame["might"] = frame["might"].apply(lambda x: x * 25)
frame["dps"] = frame["dps"].apply(lambda x: round(x * 15000))
frame["cleave"] = frame["cleave"].apply(lambda x: round(x * 20000))
frame["received"] = frame["received"].apply(lambda x: round(x * 500000))
frame["shielded"] = frame["shielded"].apply(lambda x: round(x * 250000))

frame.astype({
    "arch": numpy.int8,
    "prof": numpy.int8,
    "elite": numpy.int8,
}, copy=False)

def analyze():
    for arch in range(3):
        for prof in range(9):
            for elite in range(3):
                subframe = frame[(frame["arch"] == arch) & (frame["prof"] == prof) & (frame["elite"] == elite)]
                subframe = subframe[["might", "fury", "quickness", "alacrity", "swiftness", "vigor", "regeneration",
                                     "protection", "dps", "cleave", "received", "shielded", "crit", "flanking",
                                     "scholar", "seaweed"]]
                analysis = subframe.quantile(quantiles)
                analysis.index = (analysis.index * 100).astype(numpy.int8)
                analysis.loc["min"] = subframe.min()
                analysis.loc["mean"] = subframe.mean()
                analysis.loc["max"] = subframe.max()

                # print("Current frame: Arch", arch, "Prof", prof, "Elite", elite)
                # print(analysis)

for i in range(20):
    analyze()
