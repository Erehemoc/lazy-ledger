#!/usr/bin/env python3
"""Download Gemma 3 (GGUF) for local use with llama.cpp.

    python fetch_model.py          # gemma3:4b  (~2.5 GB, recommended)
    python fetch_model.py 1b       # gemma3:1b  (~0.8 GB, faster, less accurate)

The weights come from the public Ollama registry, the same files `ollama pull gemma3:4b`
fetches. Gemma is released under the Gemma Terms of Use: https://ai.google.dev/gemma/terms
If you already use Ollama, you can instead point --model at the blob in ~/.ollama/models/blobs.
"""
import json
import os
import sys
import urllib.request

tag = sys.argv[1] if len(sys.argv) > 1 else "4b"
reg = "https://registry.ollama.ai/v2/library/gemma3"
req = urllib.request.Request(f"{reg}/manifests/{tag}",
                             headers={"Accept": "application/vnd.docker.distribution.manifest.v2+json"})
manifest = json.load(urllib.request.urlopen(req))
layer = next(l for l in manifest["layers"] if l["mediaType"].endswith(".model"))
os.makedirs("models", exist_ok=True)
dest = os.path.join("models", f"gemma3-{tag}.gguf")
if os.path.exists(dest) and os.path.getsize(dest) == layer["size"]:
    sys.exit(f"{dest} already present")
print(f"downloading gemma3:{tag} ({layer['size'] / 1e9:.1f} GB) -> {dest}")
with urllib.request.urlopen(f"{reg}/blobs/{layer['digest']}") as r, open(dest + ".part", "wb") as f:
    done = 0
    while chunk := r.read(1 << 20):
        f.write(chunk)
        done += len(chunk)
        print(f"\r{done / layer['size']:6.1%}", end="", flush=True)
os.replace(dest + ".part", dest)
print("\ndone")
