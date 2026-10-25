"""Compare every data-only model image file against the local verified cache."""

import argparse
import hashlib
import json
import subprocess
import tarfile
from pathlib import Path
from uuid import uuid4

from citrackastra.models import MODELS, sha256, verify_model


def verify(image, directory, output):
    directory = Path(directory).resolve()
    for name in MODELS:
        verify_model(directory / name)
    expected = {p.relative_to(directory).as_posix(): sha256(p) for p in directory.rglob("*") if p.is_file()}
    container = "citrackastra-model-check-" + uuid4().hex[:8]
    subprocess.run(["docker", "create", "--name", container, image, "/verify-model-cache"], check=True, stdout=subprocess.DEVNULL)
    actual = {}
    try:
        process = subprocess.Popen(["docker", "cp", container + ":/models", "-"], stdout=subprocess.PIPE)
        with tarfile.open(fileobj=process.stdout, mode="r|") as archive:
            for member in archive:
                if not member.isfile():
                    continue
                name = member.name.removeprefix("models/")
                digest = hashlib.sha256()
                stream = archive.extractfile(member)
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
                actual[name] = digest.hexdigest()
        if process.wait() != 0:
            raise RuntimeError("Cannot read the model image contents")
        assert actual == expected, "Image model files do not match the local cache"
    finally:
        subprocess.run(["docker", "rm", container], check=True, stdout=subprocess.DEVNULL)
    image_id = subprocess.check_output(["docker", "image", "inspect", image, "--format", "{{.Id}}"], text=True).strip()
    report = {"image": image, "image_id": image_id, "status": "passed", "file_count": len(actual), "files_sha256": actual,
              "scope": "Every model-cache file compared byte-for-byte by SHA-256; all Trackastra manifests validated"}
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Verified {len(actual)} files in {image}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default="cellularimagingcf/citrackastra-models:v0.1.0")
    parser.add_argument("--model-dir", type=Path, default=Path("models"))
    parser.add_argument("--output", type=Path, default=Path("test-results/model-image-verification.json"))
    args = parser.parse_args()
    verify(args.image, args.model_dir, args.output)
