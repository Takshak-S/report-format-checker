import json

with open("debug/violations.json") as f:
    viols = json.load(f)

for i, v in enumerate(viols):
    if v["rule"] == "Invalid font size for BODY_TEXT.":
        print(f"Page {v['page']} bbox {v['bbox']} detected {v['detected']}")
        if i > 10: break

with open("debug/margin_data.json") as f:
    margin = json.load(f)
    print("Margin texts:")
    for m in margin[:5]:
        print(m["text"])
