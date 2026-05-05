import json
import os

def append_to_manifest(data, filepath="data/metadata_manifest.jsonl"):
    """Guarda una línea nueva en el archivo acumulativo."""
    try:
        filepath = os.getenv("MANIFEST_PATH", "data/metadata_manifest.jsonl")
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(json.dumps(data, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"   ❌ Error writing to manifest: {e}")