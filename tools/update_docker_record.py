"""Publish a readable record from completed container and registry checks."""

import argparse
import json
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def write_record(args):
    report = json.loads(args.validation.read_text(encoding="utf-8"))
    models = json.loads(args.models_validation.read_text(encoding="utf-8"))
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    assert report["status"] == models["status"] == "passed"
    assert len(manifest["images"]) == 3 and all(x["registry_verified"] for x in manifest["images"])
    suites = ET.parse(args.junit).getroot()
    suite_list = list(suites) if suites.tag == "testsuites" else [suites]
    unit = {key: sum(int(s.get(key, 0)) for s in suite_list) for key in ("tests", "failures", "errors", "skipped")}
    assert unit["failures"] == unit["errors"] == unit["skipped"] == 0
    record = {**report, "unit_tests": unit, "model_image": models, "publication": manifest}
    (ROOT / "docs/docker-validation.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    probe = report["gpu_probe"]
    lines = ["# Docker release validation", "", f"Recorded {report['created_utc']}. Platform: `{report['platform']}`.", "",
             f"**{unit['tests']} container unit/integration tests and {len(report['cases'])} offline public-data cases passed.** Every inference container used `--network none`.", "",
             f"GPU: {probe['gpu']}; Python {probe['python']}; PyTorch {probe['torch']}; CUDA {probe['cuda_runtime']}; Trackastra {probe['trackastra']}; napari {probe['napari']}; Divisualisation {probe['divisualisation']}.", "",
             "The same workflow also ran on CPU without GPU access. Movies were rendered headlessly with Xvfb/Mesa, encoded as H.264, decoded and checked for nonblank content.", "",
             "## Exact published artifacts", "", "| Image | Registry digest | Size (uncompressed) |", "| --- | --- | --- |"]
    for image in manifest["images"]:
        lines.append(f"| `{image['tag']}` | `{image['registry_digest']}` | {image['size_bytes'] / 1e9:.2f} GB |")
    revision = next(x["source_revision"] for x in manifest["images"] if x["tag"] == report["image"])
    lines += ["", f"Workflow source revision: `{revision}`. The full and runtime images share their application/runtime layers; the complete image adds the verified model-cache layer.", "",
              f"The separate model image matched all {models['file_count']} local cache files by SHA-256. Trackastra manifests and the pinned SAM2 backbone were verified before inference.", "",
              "## Public-data matrix", "", "| Case | Model | Selected label | Device / linking | Objects | Division events | Movies | Wall time |", "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for case in report["cases"]:
        lines.append(f"| {case['name']} | {case['model']} | {', '.join(case['selected_labels'])} | {case['device']} / {case['mode']} | {case['counts']['observations']} | {case['counts']['divisions']} | {len(case['videos'])} | {case['wall_seconds']:.1f} s |")
    lines += ["", "All cases preserved source pixels and instance labels, passed SQLite integrity checks, matched CSV/table counts, verified calibrated coordinates and matched the database/NGFF output UUID. The external-cache case used the weight-free runtime with a read-only local model cache.", "",
              "The short model matrix used six-frame GOWT1, SIM+ and U373 sequences. The longer movie case used 65 SIM+ frames and required predicted binary divisions. These calibrated CTC time series are wrapped as single-well, single-field test plates; they are compatibility checks and may overlap model training data. Counts are not biological accuracy scores.", "",
              "The multi-label example preserves the original instance markers and adds the same geometry with IDs offset by 1000 as Nuclei. Its label registry deliberately lists Nuclei before instances. The two selection cases verify the default first label and an explicit mixed-case name, with exactly one field/label result each. This is a selection check, not new biological ground truth.", "",
              "NGFF 0.4 / Zarr v2 remains required; NGFF 0.5 support is deferred. Production OMERO import, consumer plugin loading and Slurm/Apptainer submission remain deployment checks. Container validation does not establish that roundtrip.", "",
              "See [machine-readable evidence](docker-validation.json), [Docker usage](docker.md), [dataset attribution](datasets.md) and the [release attachments](https://github.com/Cellular-Imaging-Amsterdam-UMC/citrackastra/releases/tag/v0.1.1).", ""]
    (ROOT / "docs/docker-validation.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validation", type=Path, default=Path("test-results/docker-v0.1.1/docker-validation.json"))
    parser.add_argument("--models-validation", type=Path, default=Path("test-results/model-image-verification.json"))
    parser.add_argument("--manifest", type=Path, default=Path("test-results/docker-v0.1.1/image-manifest.json"))
    parser.add_argument("--junit", type=Path, default=Path("test-results/docker-unit/pytest.xml"))
    write_record(parser.parse_args())
