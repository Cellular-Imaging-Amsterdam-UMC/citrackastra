"""Explicit downloads and verified, offline local model loading."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path

MODELS = {
    "general_2d": {"dimensions": [2], "release": "v0.3.0"},
    "ctc": {"dimensions": [2], "release": "v0.3.0"},
    "general_2d_w_SAM2_features": {"dimensions": [2], "release": "v0.5.0"},
}
BASE_URL = "https://github.com/weigertlab/trackastra-models/releases/download"
SAM2_REPO = "facebook/sam2.1-hiera-base-plus"
SAM2_REVISION = "b7320756a13354e7530a63935656d35b2f91a290"
SAM2_FILE = "sam2.1_hiera_base_plus.pt"


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_model(folder):
    folder = Path(folder)
    for name in ("config.yaml", "train_config.yaml", "model.pt"):
        if not (folder / name).is_file():
            raise FileNotFoundError(f"Incomplete local model: {folder / name}. Run tools/download_models.py.")
    manifest_path = folder / "download.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Missing model integrity manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for name, expected in manifest["files"].items():
        if sha256(folder / name) != expected:
            raise ValueError(f"Model checksum mismatch: {folder / name}")
    return manifest


def download_model(name, directory):
    spec = MODELS[name]
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / name
    if destination.exists():
        return verify_model(destination)
    url = f"{BASE_URL}/{spec['release']}/{name}.zip"
    with tempfile.TemporaryDirectory(prefix=".download-", dir=directory) as temporary:
        temporary = Path(temporary)
        archive = temporary / "model.zip"
        with urllib.request.urlopen(url, timeout=120) as response, archive.open("wb") as target:
            shutil.copyfileobj(response, target)
        extracted = temporary / "extracted"
        with zipfile.ZipFile(archive) as source:
            for member in source.infolist():
                target = (extracted / member.filename).resolve()
                if not target.is_relative_to(extracted.resolve()) or (member.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError("Unsafe path in upstream model archive")
            source.extractall(extracted)
        folder = extracted / name
        files = {p.relative_to(folder).as_posix(): sha256(p) for p in sorted(folder.rglob("*")) if p.is_file()}
        manifest = {"name": name, "url": url, "archive_sha256": sha256(archive), "release": spec["release"], "files": files,
                    "license": "BSD-3-Clause (upstream Trackastra); see NOTICE.md"}
        (folder / "download.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        verify_model(folder)
        folder.rename(destination)
    return manifest


def load_model(name, directory, device):
    folder = Path(directory).resolve() / name
    verify_model(folder)
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HOME"] = str(Path(directory).resolve() / "huggingface")
    os.environ["TORCH_HOME"] = str(Path(directory).resolve() / "torch")
    if name == "general_2d_w_SAM2_features":
        from huggingface_hub import hf_hub_download

        # Upstream SAM2 asks for the default revision. The download step pins and
        # records the revision, then creates a local main ref pointing at that snapshot.
        hf_hub_download(SAM2_REPO, SAM2_FILE, cache_dir=str(Path(directory).resolve() / "huggingface/hub"), local_files_only=True)
    from trackastra.model import Trackastra

    return Trackastra.from_folder(folder, device="automatic" if device == "auto" else device)


def download_sam2(directory):
    from huggingface_hub import hf_hub_download

    cache = Path(directory).resolve() / "huggingface/hub"
    checkpoint = Path(hf_hub_download(SAM2_REPO, SAM2_FILE, revision=SAM2_REVISION, cache_dir=str(cache)))
    repository = cache / "models--facebook--sam2.1-hiera-base-plus"
    (repository / "refs").mkdir(parents=True, exist_ok=True)
    (repository / "refs/main").write_text(SAM2_REVISION, encoding="utf-8")
    record = {"repository": SAM2_REPO, "revision": SAM2_REVISION, "filename": SAM2_FILE,
              "sha256": sha256(checkpoint), "license": "Apache-2.0; see third_party/SAM2-LICENSE"}
    (Path(directory) / "sam2-backbone.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record
