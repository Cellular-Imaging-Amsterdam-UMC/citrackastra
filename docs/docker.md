# Docker images

CITrackastra uses Linux/amd64 images. All workflow variants include the three
Trackastra model adapters, SAM2 feature packages and unattended movie support.
Model weights are separated from the common runtime so they can be reused.

| Image tag | Contents | Intended use |
| --- | --- | --- |
| `cellularimagingcf/w_citrackastra:v0.1.1` | Complete workflow, local pretrained weights, SAM2 backbone and movies | Default for BIOMERO/Apptainer and Docker |
| `cellularimagingcf/w_citrackastra:v0.1.1-runtime` | CUDA runtime, all adapters and movie libraries; no weights | Mount an existing offline model cache |
| `cellularimagingcf/citrackastra-models:v0.1.1` | Checkpoints, backbone cache and license notices | Data-only build stage; not an executable workflow |

The standard workflow image is assembled from the runtime and separate model
image using `Dockerfile.with-models`. Movie support is headless: an internal
Xvfb display and Mesa render the Divisualisation view; PyTorch still uses CUDA
for tracking when requested. No interactive desktop or exposed web port is needed.
The complete image reuses the model image's cache layer at `/models`, exposed
through `/opt/models`, so pulling both images does not duplicate that layer.

## Run a segmented plate

PowerShell example, from the repository directory:

```powershell
docker pull cellularimagingcf/w_citrackastra:v0.1.1
docker run --rm --gpus all --network none --shm-size 1g `
  --mount "type=bind,source=$((Resolve-Path inputfolder).Path),target=/data/in,readonly" `
  --mount "type=bind,source=$((Resolve-Path outputfolder).Path),target=/data/out" `
  cellularimagingcf/w_citrackastra:v0.1.1 `
  --infolder /data/in --outfolder /data/out --device cuda --movie true
```

Create the input/output directories first and place complete segmented NGFF
plates in the input directory. Existing result destinations are refused.
For CPU, omit `--gpus all` and use `--device cpu`. Internet access is unnecessary
for inference; every model loads verified files from `/opt/models`.

The movie option writes both `tracking_movie.mp4` (2D trajectories, IDs and
predicted division events) and `spacetime_movie.mp4` (actual Divisualisation
spacetime rendering), plus metadata. Fields and label sets play sequentially.
The vertical display axis in the spacetime movie represents time, not physical Z.

## Reuse a local model cache

Use the runtime tag and add a read-only bind mount:

```powershell
--mount "type=bind,source=$((Resolve-Path models).Path),target=/opt/models,readonly"
```

Keep the full cache layout, including `download.json`, `sam2-backbone.json` and
the Hugging Face `snapshots`/`refs` directories. The model image preserves this
same layout at `/models` for downstream multi-stage builds.

## Rebuild and validate

```powershell
.venv\Scripts\python tools\download_models.py
.venv\Scripts\python tools\prepare_publicdata.py
.venv\Scripts\python tools\prepare_publicdata.py --datasets Fluo-N2DH-SIM+ --frames 65
.venv\Scripts\python tools\prepare_label_example.py
.venv\Scripts\python tools\build_docker.py --test-image
docker run --rm --network none --entrypoint python `
  --mount "type=bind,source=$((Resolve-Path tests).Path),target=/opt/citrackastra/tests,readonly" `
  citrackastra-tests:v0.1.1 -m pytest -q
.venv\Scripts\python tools\validate_docker.py
```

Data/model preparation needs network access; inference does not. For a rerun,
select a fresh destination with `--output-dir test-results/docker-another-run`.
Existing validation directories are deliberately refused.

The validation helper runs all inference containers with `--network none`, checks
all three models on calibrated public plates, tests CPU and CUDA, exercises
division-free and ILP modes, checks the external-cache runtime and verifies both
movies on a longer dividing-cell sequence. It compares original pixels/labels,
checks calibrated coordinates and SQLite integrity, verifies one-label default/case-insensitive selection, shared output UUIDs
and decodes encoded video frames to reject blank outputs.

The [Docker validation record](docker-validation.md) and
[GitHub release](https://github.com/Cellular-Imaging-Amsterdam-UMC/citrackastra/releases/tag/v0.1.1)
provide the measured results and exact registry digests. Docker testing does not itself establish a production
OMERO import or Slurm roundtrip.

## Label selection and format boundary

Version 0.1.1 tracks one label per field: omit the name for the first registered label, or pass `--label Nuclei` with case-insensitive matching. `--labels` is a CLI alias; the JSON key remains `labels`. Explicit names must resolve unambiguously in every field. `all` and comma-separated lists are not shortcuts. Source labels are preserved.

NGFF 0.4 / Zarr v2 remains required. NGFF 0.5 / Zarr v3 support is deferred, consistent with the currently documented BIOMERO.shallower format boundary. See the [upstream README](https://github.com/NL-BioImaging/BIOMERO.shallower#readme).
