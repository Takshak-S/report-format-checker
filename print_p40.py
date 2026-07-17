import json
with open("debug/margin_data.json") as f:
    data = json.load(f)
for p in data:
    if p["page"] == 40 and any(r > 533 for r in p["right_edges"]):
        print(p["text"])
