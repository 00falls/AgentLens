"""Download one pinned embedding snapshot; never download model code."""

import hashlib
import json

from huggingface_hub import snapshot_download

from agentlens.config import Settings
from agentlens.knowledge import EMBEDDING_MODEL, EMBEDDING_REVISION

FILES = [
    "config.json",
    "config_sentence_transformers.json",
    "model.safetensors",
    "modules.json",
    "sentence_bert_config.json",
    "special_tokens_map.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "vocab.txt",
    "1_Pooling/config.json",
]


def main():
    target = Settings().embedding_path
    snapshot_download(
        EMBEDDING_MODEL, revision=EMBEDDING_REVISION, local_dir=target, allow_patterns=FILES
    )
    artifacts = {name: hashlib.sha256((target / name).read_bytes()).hexdigest() for name in FILES}
    (target / "artifacts.json").write_text(json.dumps(artifacts, indent=2) + "\n", encoding="utf-8")
    print(f"Downloaded {EMBEDDING_MODEL}@{EMBEDDING_REVISION} to {target}")


if __name__ == "__main__":
    main()
