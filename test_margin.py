import json
with open("debug/violations.json") as f:
    viols = json.load(f)
for v in viols:
    if "margin" in v["rule"].lower():
        print(f"Page {v['page']} - {v['reason']}")
