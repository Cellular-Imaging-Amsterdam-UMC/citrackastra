"""Push exactly the image artifacts identified by successful validation reports."""

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path


def inspect(image):
    return json.loads(subprocess.check_output(["docker", "image", "inspect", image], text=True))[0]


def publish(args):
    report = json.loads(args.validation.read_text(encoding="utf-8"))
    models = json.loads(args.models_validation.read_text(encoding="utf-8"))
    if report["status"] != "passed" or models["status"] != "passed":
        raise RuntimeError("Both workflow and model-image validation must pass before publication")
    artifacts = [(models["image"], models["image_id"]), (report["runtime_image"], report["runtime_image_id"]), (report["image"], report["image_id"])]
    for image, expected in artifacts:
        if inspect(image)["Id"] != expected:
            raise RuntimeError(f"Image changed after validation: {image}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    records = {"platform": "linux/amd64", "images": [], "validation_sha256": hashlib.sha256(args.validation.read_bytes()).hexdigest(),
               "model_validation_sha256": hashlib.sha256(args.models_validation.read_bytes()).hexdigest()}
    for image, expected in artifacts:
        print(f"Publishing verified artifact {image}", flush=True)
        subprocess.run(["docker", "push", image], check=True)
        remote = subprocess.check_output(["docker", "buildx", "imagetools", "inspect", image], text=True)
        digest = re.search(r"^Digest:\s+(sha256:[a-f0-9]+)", remote, re.M)
        if not digest:
            raise RuntimeError(f"Registry did not report an image digest for {image}")
        info = inspect(image)
        local_digests = {value.split("@", 1)[1] for value in info.get("RepoDigests", [])}
        if digest[1] not in local_digests:
            raise RuntimeError(f"Registry digest does not match the pushed local image: {image}")
        records["images"].append({"tag": image, "image_id": expected, "registry_digest": digest[1], "size_bytes": info["Size"],
                                  "source_revision": (info["Config"].get("Labels") or {}).get("org.opencontainers.image.revision"),
                                  "registry_verified": True})
        args.output.write_text(json.dumps(records, indent=2), encoding="utf-8")
    print(f"Published and verified {len(artifacts)} images: {args.output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validation", type=Path, default=Path("test-results/docker-v0.1.0/docker-validation.json"))
    parser.add_argument("--models-validation", type=Path, default=Path("test-results/model-image-verification.json"))
    parser.add_argument("--output", type=Path, default=Path("test-results/docker-v0.1.0/image-manifest.json"))
    publish(parser.parse_args())
