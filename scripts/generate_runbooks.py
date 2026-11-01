"""Materialize synthetic runbooks from their single authoring source."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    folder = ROOT / "datasets/runbooks"
    catalog = json.loads((folder / "catalog.json").read_text(encoding="utf-8"))
    for doc in catalog["documents"]:
        content = f"# {doc['title']}\n\n"
        content += "\n\n".join(
            f"## {section['heading']}\n\n{section['text']}" for section in doc["sections"]
        )
        (folder / f"{doc['id']}.md").write_text(content + "\n", encoding="utf-8")
    print(f"Generated {len(catalog['documents'])} synthetic runbooks")


if __name__ == "__main__":
    main()
