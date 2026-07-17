import json

with open("debug/margin_data.json") as f:
    data = json.load(f)

for p in data:
    for i, right in enumerate(p["right_edges"]):
        if right > 533.276:
            print(f"Page {p['page']} has right edge {right} in {p['type']}")
