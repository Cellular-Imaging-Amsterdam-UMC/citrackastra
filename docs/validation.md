# Local validation record

## Standalone timelapse and frame I/O update — 27 October 2026

The current source passed 50 automated tests, including standalone-image and
multi-field HCS routing, source preservation, calibration/time/Z validation,
global normalization equivalence and retention of unmatched detections.

Real CUDA inference with `general_2d` and `greedy_nodiv` processed the same
six-frame Fluo-N2DH-SIM+ input as an HCS field and a standalone NGFF image.
Both produced 180 observations, 30 tracks and 150 links. Tracked pixels were
identical between both layouts; source pixels and labels were preserved and
SQLite integrity checks passed. Calibration was 0.125 micrometers/pixel and
1740 seconds/frame, copied from the existing public-data provenance.
The checkpoint archive SHA-256 was
`35cefd8634860d1dd43bcdcbdef7ae0caa24445f19bcfd35ec6b19039f2cd876`.

This is a compatibility check using CTC reference markers, not an independent
accuracy benchmark. It does not establish completion of a production Slurm run.
The published `v0.1.1` image still has the older plate-only implementation.

The local Apptainer image `v0.1.1-local.20261027` also passed both input layouts
with the real model and both requested movie outputs, without mounting source
code over the image. Its SHA-256 is
`6974a0b7bbef0926544fa9636c4dfdbdde93246924d0488a7c4d2453c4acec33`.
Regenerating the BIOMERO job script preserves selection of this distinct image
version. A full 700-frame BIOMERO run was submitted separately; its result is
not claimed by these smoke checks.

## Job 47 movie recovery — 27 October 2026

The 700-frame standalone timelapse finished tracking before Slurm job 47
timed out during movie postprocessing. SQLite integrity was `ok`, with 11,742
tracks, 76,997 observations and 65,255 links over frames 0–699. Movie recovery
used that existing database and the existing tracked labels; inference was not
repeated. All tracking table rows and CSV bytes matched the pre-recovery backup.

The movie renderer now caps the napari Dask cache, disables layer caching and
periodically collects rendering objects. It closes its disposable viewer without
reverting the spacetime lift: reverting first changes image/label dimensionality
while the viewer still displays 3D, which can materialize the whole timelapse as
a volume. The corrected full run remained around 0.7 GiB resident memory while
rendering and exited successfully. Both MP4s decoded completely: 2,100 frames /
175 seconds for the conventional view and 1,412 frames / 117.66 seconds for the
spacetime view, both at 12 fps. No ground-truth accuracy claim is implied.

All 50 automated tests passed after this correction. The rebuilt local image
passed movie-only checks for both six-frame HCS and standalone outputs, without
source binds or new tracking, and a CUDA device/allocation check. The image
registered as `v0.1.1-local.20261027` now has SHA-256
`3bbd74344a29cf2976f42da19036feed7ed25544ebdf4ae10764b578ba9f9087`.
The earlier image above is retained separately as a recovery backup. The local
deployment allows two hours for future tracking-plus-movie jobs.

The recovered BIOMERO workflow also completed its local OMERO roundtrip.
Image 201 in Dataset 51 (`Tracking`) has all 700 timepoints and exposes the new
`labels_spots_channel_1_tracks` label set. The first and last source-image planes
read through OMERO matched Image 153 exactly. The four OMERO tables were checked
against the SQLite row counts above, and both complete MP4s, SQLite and JSON
provenance were attached to the dataset. Slurm task 48 performed only result
normalization; tracking was not repeated. Workflow history records completion
of recovery while original Slurm job 47 retains its `TIMEOUT` accounting state.

## Earlier release validation

Verified on **25 October 2026** on Windows with Python 3.11.14.

Device: **NVIDIA GeForce RTX 3060 (12 GB)**; PyTorch `2.11.0+cu126`; CUDA runtime `12.6`.

- 24 automated tests passed for the original HCS-only release.
- Both consumer skills passed the skill-creator frontmatter/resource validator.
- The Bilayers descriptor generated CLI arguments accepted by the workflow parser.
- Four English Pages documents, local links, gallery assets and theme controls passed static checks.
- Interactive browser checks covered actual trajectory timelines and movie presentation.
- All three model checkpoints and the SAM2.1 backbone were downloaded and verified locally.

## Actual CUDA model runs

| Input | Model | Frames | Observations | Tracklets | Predicted divisions | Tracking stage | Peak PyTorch CUDA allocation |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Fluo-N2DH-GOWT1-01-6frames.ome.zarr | general_2d | 6 | 138 | 23 | not counted | 1.04 s | 51.8 MiB |
| Fluo-N2DH-SIM+-01-6frames.ome.zarr | general_2d | 6 | 180 | 30 | not counted | 0.73 s | 52.3 MiB |
| PhC-C2DH-U373-01-6frames.ome.zarr | general_2d | 6 | 36 | 6 | not counted | 0.42 s | 50.6 MiB |
| Fluo-N2DH-GOWT1-01-6frames.ome.zarr | ctc | 6 | 138 | 23 | not counted | 0.73 s | 116.4 MiB |
| Fluo-N2DH-SIM+-01-6frames.ome.zarr | ctc | 6 | 180 | 30 | not counted | 0.58 s | 117.2 MiB |
| PhC-C2DH-U373-01-6frames.ome.zarr | ctc | 6 | 36 | 6 | not counted | 0.48 s | 114.5 MiB |
| Fluo-N2DH-GOWT1-01-6frames.ome.zarr | general_2d_w_SAM2_features | 6 | 138 | 23 | not counted | 3.04 s | 729.2 MiB |
| Fluo-N2DH-SIM+-01-6frames.ome.zarr | general_2d_w_SAM2_features | 6 | 180 | 30 | not counted | 2.09 s | 730.4 MiB |
| PhC-C2DH-U373-01-6frames.ome.zarr | general_2d_w_SAM2_features | 6 | 36 | 6 | not counted | 1.94 s | 730.2 MiB |
| Fluo-N2DH-SIM+-01-65frames.ome.zarr | general_2d | 65 | 2607 | 84 | 21 | 5.84 s | 53.8 MiB |
| Fluo-N2DH-GOWT1-01-92frames.ome.zarr | general_2d | 92 | 2058 | 29 | 1 | 9.89 s | 51.9 MiB |

Tracking-stage time includes source copying, model associations and database-row preparation. Optional movie rendering and final exports are excluded. GPU figures measure peak PyTorch allocation, not total device use.

All runs preserved original source pixels and instance labels and passed SQLite integrity checks. The nine six-frame model runs produced Divisualisation spacetime movies. The two full-length runs produced both conventional 2D tracking and spacetime MP4s. Representative encoded frames were decoded and visually inspected; blank OpenGL renders are rejected.

## Longer division examples

- **Fluo-N2DH-SIM+-01-65frames.ome.zarr**: 28 complete binary reference events in the input lineage metadata; 21 predicted binary events. The reference and prediction counts are not matched-event precision/recall.
- **Fluo-N2DH-GOWT1-01-92frames.ome.zarr**: 2 complete binary reference events in the input lineage metadata; 1 predicted binary events. The reference and prediction counts are not matched-event precision/recall.

## Scientific and deployment limits

The public CTC time series are packaged as single-well, single-field test plates. They are not original multiwell screening plates. TRA masks are reference markers, not necessarily complete cell or nuclear segmentation. CTC data may overlap pretrained-model training; these tests establish pipeline execution and file compatibility, not independent biological accuracy. Multi-field isolation is covered by synthetic integration tests.

Movie playback is separate from acquisition timing. The Divisualisation vertical coordinate is a display of time, not a physical Z measurement. No independent ground-truth error coloring is claimed.

This record describes local Windows inference with greedy linking and native OpenGL movies. Docker CPU/CUDA, ILP, division-free and headless movie checks are recorded separately in [Docker validation](docker-validation.md) and the [release artifacts](https://github.com/Cellular-Imaging-Amsterdam-UMC/citrackastra/releases/tag/v0.1.0). Production OMERO import and Slurm roundtrip validation remain deployment checks.

The repository manifest registers the OMERO/BIOMERO skills; loading them in a running consumer remains part of that installation's normal workflow/plugin configuration.

See [datasets.md](datasets.md) for source attribution and calibration, and [assets/validation.json](assets/validation.json) for sanitized machine-readable evidence.
