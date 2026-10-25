# Local validation record

Verified on **25 October 2026** on Windows with Python 3.11.14.

Device: **NVIDIA GeForce RTX 3060 (12 GB)**; PyTorch `2.11.0+cu126`; CUDA runtime `12.6`.

- 24 automated tests passed with the final plate-only contract.
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
