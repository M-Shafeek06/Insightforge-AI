import json
from pathlib import Path

folders = [
    Path("../data/metadata/dataset_versions"),
    Path("../data/processed/cleaning_plans"),
    Path("../data/raw"),
]

for folder in folders:
    print(f"\nFOLDER: {folder.resolve()}")

    if not folder.exists():
        print("Directory does not exist.")
        continue

    for file in sorted(folder.glob("*.json")):
        try:
            data = json.loads(file.read_text(encoding="utf-8"))

            if isinstance(data, dict):
                print(f"{file.name}: {list(data.keys())}")
            else:
                print(f"{file.name}: {type(data).__name__}")

        except Exception as error:
            print(f"{file.name}: ERROR - {error}")
