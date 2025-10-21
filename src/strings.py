import json

with open("src/string.json", "r", encoding="utf-8") as f:
    strings = json.load(f)


def get_string(key: str) -> str:
    return strings.get(key, "")
