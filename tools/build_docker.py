"""Build the release's runtime, model cache and complete headless workflow.

No images are published by this helper. Run validate_docker.py before pushing.
"""

import argparse
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(*args):
    subprocess.run(args, cwd=ROOT, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default="v0.1.0")
    parser.add_argument("--org", default="cellularimagingcf")
    parser.add_argument("--test-image", action="store_true")
    args = parser.parse_args()
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    runtime = f"{args.org}/w_citrackastra:{args.version}-runtime"
    models = f"{args.org}/citrackastra-models:{args.version}"
    complete = f"{args.org}/w_citrackastra:{args.version}"
    run("docker", "build", "--platform", "linux/amd64", "--target", "runtime", "--build-arg", f"VCS_REF={revision}", "-t", runtime, "-f", "Dockerfile", ".")
    run("docker", "build", "--platform", "linux/amd64", "-t", models, "-f", "Dockerfile.models", ".")
    run("docker", "build", "--platform", "linux/amd64", "--build-arg", f"RUNTIME_IMAGE={runtime}", "--build-arg", f"MODEL_IMAGE={models}", "-t", complete, "-f", "Dockerfile.with-models", ".")
    if args.test_image:
        run("docker", "build", "--platform", "linux/amd64", "--target", "tests", "--build-arg", f"VCS_REF={revision}", "-t", f"citrackastra-tests:{args.version}", "-f", "Dockerfile", ".")
    print(f"Built {complete}, {runtime} and {models}. Validate before publishing.")


if __name__ == "__main__":
    main()
