import json
from collections import Counter

with open("debug/violations.json") as f:
    viols = json.load(f)

print(Counter([v["rule"] for v in viols]))
print(Counter([v["reason"] for v in viols]))
print(Counter([v["confidence"] < 0.75 for v in viols]))

