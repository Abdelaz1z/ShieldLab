# validate_data.py
# Loads every JSON data file to confirm valid syntax and reports a short summary.
import json, os, glob

DATA = r"D:\Projects\Master\Master-26\Control Claude Program\radshield\data"
ok = True
for path in sorted(glob.glob(os.path.join(DATA, "*.json"))):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        print(f"OK   {os.path.basename(path):28s} top-level keys: {len(data)}")
    except Exception as e:
        ok = False
        print(f"FAIL {os.path.basename(path):28s} {e}")
print("ALL VALID" if ok else "ERRORS PRESENT")
