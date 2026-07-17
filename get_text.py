import json
with open("debug/margin_data.json") as f:
    data = json.load(f)
for p in data:
    if p["id"] == "para_13571":
        print(repr(p["text"]))
