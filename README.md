# CITrackastra

**Calibrated 2D time-series plate tracking for OME-Zarr, Bilayers and BIOMERO.**

CITrackastra uses [Trackastra](https://github.com/weigertlab/trackastra) to link
existing instance segmentations across time. Segment upstream with
[CISegmentation](https://github.com/Cellular-Imaging-Amsterdam-UMC/cisegmentation)
or another instance model. Input is restricted to **NGFF HCS plates with 2D time
series**: every field needs T ≥ 2, Z absent/singleton and calibrated XY pixels.
Standalone images, static plates and volumes are rejected without projection.

[Documentation & interactive examples](https://cellular-imaging-amsterdam-umc.github.io/citrackastra/)
· [Dataset sources](docs/datasets.md) · [Validation](docs/validation.md)

## Local setup

On Windows, with [uv](https://docs.astral.sh/uv/) installed:

```bat
create_env.cmd
install_cuda.cmd
.venv\Scripts\python tools\download_models.py
.venv\Scripts\python tools\prepare_publicdata.py
.venv\Scripts\python wrapper.py --local --infolder publicdata\plates --outfolder outputfolder --device cuda
```

The environment uses Python 3.11. `install_cuda.cmd` selects matching PyTorch
2.11.0 / torchvision 0.26.0 wheels with CUDA 12.6. For CPU use `--device cpu`.
Linux setup: create a Python 3.11 virtual environment, install the appropriate
PyTorch wheels, then `pip install -e '.[dev]'` and use the same Python scripts.

`tools/download_models.py` explicitly downloads **all three** upstream pretrained
tracking checkpoints (`general_2d`, `ctc`, `general_2d_w_SAM2_features`) into
ignored `models/`, plus the pinned SAM2.1 backbone into its local Hugging Face
cache. URLs, revisions and SHA-256 hashes are retained. Existing model files are
verified before reuse. No model is silently downloaded during inference.

Run `install_sam2.cmd` for the optional SAM2 feature runtime before selecting
`--model general_2d_w_SAM2_features`. This model needs both its tracking checkpoint
and the cached SAM2.1 backbone. All three models are restricted to 2D plate
fields by this adapter, including the upstream CTC model.

For your own segmented plate:

```bat
.venv\Scripts\python wrapper.py --infolder inputfolder --outfolder outputfolder --labels labels_cells --channel 1 --model general_2d --mode greedy --device cuda
```

`--labels all` tracks each input label group independently. Field and label-set
boundaries are never linked. Channels are one-based. Linking modes are `greedy`
(divisions allowed), `greedy_nodiv` and `ilp` (installed solver stack; Gurobi may
be used if licensed). `--parameters` accepts a JSON object; unknown CLI options
are rejected. See [the workflow reference](skills/use-citrackastra-workflow/references/PARAMETERS.md).

## Outputs

One new result directory is published for each input plate:

```text
outputfolder/<plate>__citrackastra/
  <plate>__citrackastra.ome.zarr/
  tracking.sqlite
  fields.csv
  tracks.csv
  observations.csv
  links.csv
  provenance.json
  tracking_movie.mp4   # optional
  spacetime_movie.mp4  # optional
  movie.json          # optional
```

**OME-Zarr + SQLite are the primary results.** The copied plate preserves all
source pixels, original labels, plate/well metadata and calibration. Each field
receives `labels/<input_label>_tracks`. The SQLite database stores tracklets,
observations, links, parentage, calibrated motion, schema identity and provenance.
CSV exports support quick inspection; the movie supports visual review.

Track IDs are local to `(field_id, track_id)`. Original instance IDs are retained
separately. CTC tracklets split at gaps and divisions; `parent_kind` distinguishes
them. Physical coordinates use ordered NGFF transforms in micrometers; unknown
time calibration gives frames and micrometers/frame. Singleton speeds are NULL.
The database output UUID matches `citrackastra.output_store_uuid` in the result
store. See [schema and SQL](skills/analyze-citrackastra-tracks/references/SCHEMA.md).

Completed destinations cannot be overwritten. All artifacts publish together by
a same-filesystem directory rename after success. A failed run retains a hidden
`.partial-*` directory and `FAILED.json`, which are not completed results.

## Optional Divisualisation movie

```bat
install_movie.cmd
.venv\Scripts\python wrapper.py --infolder inputfolder --outfolder outputfolder --device cuda --movie true --movie-fps 12
```

This uses the actual [Divisualisation](https://github.com/bentaculum/divisualisation/)
`SpacetimeLift` engine in napari. It writes **two H.264 MP4s per input plate**:
`tracking_movie.mp4` shows conventional 2D trajectories, IDs and predicted division
events; `spacetime_movie.mp4` shows the Divisualisation view. Each contains
sequential segments for fields and label sets. A sweep reveals the
predicted trajectories through time. The lifted vertical coordinate represents
time, not physical Z. Playback FPS is separate from acquisition time calibration.
No independent ground-truth error scoring is implied. Images are stretched only
for display; source pixels remain unchanged.

Windows renders using a hidden native Qt/OpenGL context. Unattended Linux needs
Xvfb with Mesa/GLX; `Dockerfile.movie` prepares that runtime. The base workflow
does not require movie dependencies when `--movie false` (the default).
An isolated renderer can be selected with `CITRACKASTRA_MOVIE_PYTHON`.

## Bilayers, BIOMERO and model images

`config.yaml` follows the CISegmentation Bilayers descriptor pattern:

```bat
.venv\Scripts\python bilayers_cli.py validate
.venv\Scripts\python bilayers_cli.py generate
```

The container expects `/data/in`, `/data/out` and the offline cache at
`/opt/models`. Discover result stores recursively inside plate result directories
and attach matching databases, CSVs and movies to the corresponding plate.
The descriptor declares the database and optional movie outputs explicitly.

- `Dockerfile`: headless CUDA tracking runtime.
- `Dockerfile.models`: separate offline cache image with licenses.
- `Dockerfile.with-models`: combine runtime and model image later.
- `Dockerfile.movie`: optional unattended Divisualisation rendering runtime.

These are prepared recipes and planned image tags. **No Docker build, Docker Hub
publication or production OMERO/Slurm roundtrip has been performed.**
Bind-mounting the local cache is also supported. Install SAM2 extras in a runtime
that will expose the corresponding model option.

## Agent skills

`plugin.json` uses the same consumer extension as CISegmentation:

- [analyze-citrackastra-tracks](skills/analyze-citrackastra-tracks/SKILL.md):
  automatic SQLite attachment analysis for `omero-analysis` (`omero.analysis`),
  schema-aware SQL, physical units and verified image/label navigation.
- [use-citrackastra-workflow](skills/use-citrackastra-workflow/SKILL.md):
  selection, submission, monitoring and output verification for `omero-biomero`.

Registration in this repository does not change a running OMERO installation;
the consumer must load this plugin revision using its normal integration.

## Tests, data and limits

```bat
test.cmd
.venv\Scripts\python tools\validate_local.py --device cuda
.venv\Scripts\python tools\build_site.py --validation test-results/public/validation.json
.venv\Scripts\python tools\check_site.py docs
```

The public test inputs are calibrated CTC TIFF time series converted losslessly
to NGFF 0.4 / Zarr v2 **single-well, single-field test plates**. They are not
original screening plates. Source metadata, checksums, licensing and limitations
are recorded in [datasets.md](docs/datasets.md). Reference TRA markers are not
complete cell/nuclear masks. Training overlap means smoke runs are not independent
biological accuracy benchmarks. Multi-field isolation has synthetic integration
coverage.

Inference currently holds each field's full time sequence in memory. Array
preflight is conservative; graph/model costs are additional and density dependent.
`--max-memory-gb` is not a hard RAM or VRAM limit. Inference uses the original
pixel grid: calibrated output does not resample anisotropic pixels for the model.

## License and citation

CITrackastra is **BSD-3-Clause**; see [LICENSE](LICENSE).
[Trackastra](https://github.com/weigertlab/trackastra) and its
[pretrained-model repository](https://github.com/weigertlab/trackastra-models)
are BSD-3-Clause, with their original licenses retained under `third_party/`.
Divisualisation and the reused CI styling/descriptor helper retain their MIT
licenses. SAM2 has its separate Apache-2.0 license and attribution. Dataset
licenses remain separate. See [NOTICE.md](NOTICE.md).

Please cite Benjamin Gallusser and Martin Weigert,
[Trackastra: Transformer-based cell tracking for live-cell microscopy](https://www.ecva.net/papers/eccv_2024/papers_ECCV/papers/09819.pdf),
ECCV 2024, pp. 467–484. When using SAM2 features, also follow the citations in
the upstream [model catalog](https://github.com/weigertlab/trackastra/blob/main/trackastra/model/pretrained.json)
and [SAM2](https://github.com/facebookresearch/sam2).
