# Docker release validation

Recorded 2026-10-25T18:52:25.098692+00:00. Platform: `linux/amd64`.

**24 container unit/integration tests and 13 offline public-data cases passed.** Every inference container used `--network none`.

GPU: NVIDIA GeForce RTX 3060; Python 3.12.3; PyTorch 2.11.0+cu126; CUDA 12.6; Trackastra 0.5.6; napari 0.8.0; Divisualisation 0.1.0.

The same workflow also ran on CPU without GPU access. Movies were rendered headlessly with Xvfb/Mesa, encoded as H.264, decoded and checked for nonblank content.

## Exact published artifacts

| Image | Registry digest | Size (uncompressed) |
| --- | --- | --- |
| `cellularimagingcf/citrackastra-models:v0.1.0` | `sha256:c441a1a470471cd515447347603592c63528ca096cd1117a8cac6368ad725291` | 0.96 GB |
| `cellularimagingcf/w_citrackastra:v0.1.0-runtime` | `sha256:52cc6c647f3f944be6313e4192f9d6e47b1b6fa89b4ddafdd0c49ba55b257297` | 13.68 GB |
| `cellularimagingcf/w_citrackastra:v0.1.0` | `sha256:ae3defe99d8f4a8ab43bc9fed8267c9cfa1fec7b8135e9aa54ece3299ff81e36` | 14.63 GB |

Workflow source revision: `bb82ef456ea3eeaf7fbdbebc0cb9d554df381ddf`. The full and runtime images share their application/runtime layers; the complete image adds the verified model-cache layer.

The separate model image matched all 17 local cache files by SHA-256. Trackastra manifests and the pinned SAM2 backbone were verified before inference.

## Public-data matrix

| Case | Model | Device / linking | Objects | Division events | Movies | Wall time |
| --- | --- | --- | --- | --- | --- | --- |
| cuda-general_2d-0 | general_2d | cuda / greedy | 138 | 0 | 0 | 14.8 s |
| cuda-general_2d-1 | general_2d | cuda / greedy | 180 | 0 | 0 | 12.1 s |
| cuda-general_2d-2 | general_2d | cuda / greedy | 36 | 0 | 0 | 11.4 s |
| cuda-ctc-0 | ctc | cuda / greedy | 138 | 0 | 0 | 13.4 s |
| cuda-ctc-1 | ctc | cuda / greedy | 180 | 0 | 0 | 11.5 s |
| cuda-ctc-2 | ctc | cuda / greedy | 36 | 0 | 0 | 10.6 s |
| cuda-general_2d_w_SAM2_features-0 | general_2d_w_SAM2_features | cuda / greedy | 138 | 0 | 2 | 29.5 s |
| cuda-general_2d_w_SAM2_features-1 | general_2d_w_SAM2_features | cuda / greedy | 180 | 0 | 0 | 13.2 s |
| cuda-general_2d_w_SAM2_features-2 | general_2d_w_SAM2_features | cuda / greedy | 36 | 0 | 0 | 12.2 s |
| cpu-no-divisions-movies | general_2d | cpu / greedy_nodiv | 138 | 0 | 2 | 25.7 s |
| cpu-ilp | general_2d | cpu / ilp | 138 | 0 | 0 | 12.1 s |
| cuda-long-divisions-movies | general_2d | cuda / greedy | 2607 | 21 | 2 | 75.6 s |
| runtime-external-model-cache | general_2d | cpu / greedy | 138 | 0 | 0 | 12.5 s |

All cases preserved source pixels and instance labels, passed SQLite integrity checks, matched CSV/table counts, verified calibrated coordinates and matched the database/NGFF output UUID. The external-cache case used the weight-free runtime with a read-only local model cache.

The short model matrix used six-frame GOWT1, SIM+ and U373 sequences. The longer movie case used 65 SIM+ frames and required predicted binary divisions. These calibrated CTC time series are wrapped as single-well, single-field test plates; they are compatibility checks and may overlap model training data. Counts are not biological accuracy scores.

Production OMERO import, consumer plugin loading and Slurm/Apptainer submission remain deployment checks. Container validation does not establish that roundtrip.

See [machine-readable evidence](docker-validation.json), [Docker usage](docker.md), [dataset attribution](datasets.md) and the [release attachments](https://github.com/Cellular-Imaging-Amsterdam-UMC/citrackastra/releases/tag/v0.1.0).
