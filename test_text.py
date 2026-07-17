import json

with open("debug/violations.json") as f:
    viols = json.load(f)

for v in viols:
    if v["id"].startswith("M"):
        # We want the text for this dom_id.
        pass

with open("debug/margin_data.json") as f:
    margin_data = json.load(f)

for m in margin_data:
    for v in viols:
        if v["id"].startswith("M") and m["id"] == v["dom_id"]:
            print(f"{v['id']} (Page {m['page']}): {m['text']}")
