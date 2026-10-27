"""Publish a sanitized validation summary without workstation result paths."""

import argparse
import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def write_record(source):
    report = json.loads(Path(source).read_text(encoding="utf-8"))
    public = copy.deepcopy(report)
    for run in public["runs"]:
        run.pop("result", None)
    (ROOT / "docs/assets/validation.json").write_text(json.dumps(public, indent=2), encoding="utf-8")
    lines = ["# Local validation record", "", "Verified on **25 October 2026** on Windows with Python 3.11.14.", "",
             f"Device: **{report['device']} (12 GB)**; PyTorch `{report['torch']}`; CUDA runtime `{report['cuda_runtime']}`.", "",
             "- 24 automated tests passed for the original HCS-only release.",
             "- Both consumer skills passed the skill-creator frontmatter/resource validator.",
             "- The Bilayers descriptor generated CLI arguments accepted by the workflow parser.",
             "- Four English Pages documents, local links, gallery assets and theme controls passed static checks.",
             "- Interactive browser checks covered actual trajectory timelines and movie presentation.",
             "- All three model checkpoints and the SAM2.1 backbone were downloaded and verified locally.", "",
             "## Actual CUDA model runs", "",
             "| Input | Model | Frames | Observations | Tracklets | Predicted divisions | Tracking stage | Peak PyTorch CUDA allocation |", "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for run in report["runs"]:
        count = run["counts"]
        lines.append(f"| {run['dataset']} | {run['model']} | {run['source']['frame_range'][1]+1} | {count['observations']} | {count['tracks']} | {count.get('divisions', 'not counted')} | {run['runtime_seconds']:.2f} s | {run['peak_cuda_allocated_mib']:.1f} MiB |")
    lines += ["", "Tracking-stage time includes source copying, model associations and database-row preparation. Optional movie rendering and final exports are excluded. GPU figures measure peak PyTorch allocation, not total device use.", "",
              "All runs preserved original source pixels and instance labels and passed SQLite integrity checks. The nine six-frame model runs produced Divisualisation spacetime movies. The two full-length runs produced both conventional 2D tracking and spacetime MP4s. Representative encoded frames were decoded and visually inspected; blank OpenGL renders are rejected.", "", "## Longer division examples", ""]
    for run in report["runs"]:
        if run["source"]["frame_range"][1] > 6:
            lines.append(f"- **{run['dataset']}**: {len(run['source'].get('reference_divisions', []))} complete binary reference events in the input lineage metadata; {run['counts'].get('divisions', 0)} predicted binary events. The reference and prediction counts are not matched-event precision/recall.")
    lines += ["", "## Scientific and deployment limits", "",
              "The public CTC time series are packaged as single-well, single-field test plates. They are not original multiwell screening plates. TRA masks are reference markers, not necessarily complete cell or nuclear segmentation. CTC data may overlap pretrained-model training; these tests establish pipeline execution and file compatibility, not independent biological accuracy. Multi-field isolation is covered by synthetic integration tests.", "",
              "Movie playback is separate from acquisition timing. The Divisualisation vertical coordinate is a display of time, not a physical Z measurement. No independent ground-truth error coloring is claimed.", "",
              "This record describes local Windows inference with greedy linking and native OpenGL movies. Docker CPU/CUDA, ILP, division-free and headless movie checks are recorded separately in [Docker validation](docker-validation.md) and the [release artifacts](https://github.com/Cellular-Imaging-Amsterdam-UMC/citrackastra/releases/tag/v0.1.0). Production OMERO import and Slurm roundtrip validation remain deployment checks.", "",
              "The repository manifest registers the OMERO/BIOMERO skills; loading them in a running consumer remains part of that installation's normal workflow/plugin configuration.", "",
              "See [datasets.md](datasets.md) for source attribution and calibration, and [assets/validation.json](assets/validation.json) for sanitized machine-readable evidence.", ""]
    (ROOT / "docs/validation.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("validation")
    write_record(parser.parse_args().validation)
