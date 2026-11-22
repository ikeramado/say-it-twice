"""Response cache keyed by (model, prefix and prompt hash, sample index), under runs/cache/."""

import hashlib
import json
import os
import tempfile
from pathlib import Path


def prompt_hash(prompt, prefix=None):
    # Without a prefix the key is the prompt's hash alone, so earlier cache files still match.
    text = prompt if prefix is None else f"prefix\0{prefix}\0prompt\0{prompt}"
    return hashlib.sha256(text.encode()).hexdigest()


class Cache:
    def __init__(self, root):
        self.root = Path(root)

    def path(self, model, prompt, sample, prefix=None):
        return self.root / f"{model}-{prompt_hash(prompt, prefix)}-{sample}.json"

    def get(self, model, prompt, sample, prefix=None):
        p = self.path(model, prompt, sample, prefix)
        return json.loads(p.read_text()) if p.exists() else None

    def put(self, model, prompt, sample, entry, prefix=None):
        p = self.path(model, prompt, sample, prefix)
        p.parent.mkdir(parents=True, exist_ok=True)
        # A unique temporary name per write, then an atomic rename: threads never share one.
        fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=p.stem + ".", suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                f.write(json.dumps(entry))
            os.replace(tmp, p)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
