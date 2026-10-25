"""Download all upstream pretrained Trackastra checkpoints into a local cache."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from citrackastra.models import MODELS, download_model, download_sam2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", type=Path, default=Path("models"))
    parser.add_argument("--models", nargs="+", choices=list(MODELS), default=list(MODELS))
    args = parser.parse_args()
    for name in args.models:
        result = download_model(name, args.model_dir)
        print(json.dumps({"model": name, "sha256": result["archive_sha256"]}), flush=True)
    if "general_2d_w_SAM2_features" in args.models:
        print(json.dumps(download_sam2(args.model_dir)), flush=True)


if __name__ == "__main__":
    main()
