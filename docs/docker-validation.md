# Docker release validation

Recorded 2026-10-26T09:55:15.628478+00:00. Platform: `linux/amd64`.

**39 container unit/integration tests and 15 offline public-data cases passed.** Every inference container used `--network none`.

GPU: NVIDIA GeForce RTX 3060; Python 3.12.3; PyTorch 2.11.0+cu126; CUDA 12.6; Trackastra 0.5.6; napari 0.8.0; Divisualisation 0.1.0.

The same workflow also ran on CPU without GPU access. Movies were rendered headlessly with Xvfb/Mesa, encoded as H.264, decoded and checked for nonblank content.

## Exact published artifacts

| Image | Registry digest | Size (uncompressed) |
| --- | --- | --- |
| `cellularimagingcf/citrackastra-models:v0.1.1` | `sha256:3e97cb7f65533ea66a19a168b6a8a6e6fba2d072fd3ea3acaea422ae7717b8ac` | 0.96 GB |
| `cellularimagingcf/w_citrackastra:v0.1.1-runtime` | `sha256:cfc426e14d01aa7723d343e3ba3810b22df88b44ab4fbcfd9774d82e6fea3909` | 13.68 GB |
| `cellularimagingcf/w_citrackastra:v0.1.1` | `sha256:ac40cee56a3683672342a5ba09db8c81ff4303950862c62d783f2273eb5f4746` | 14.64 GB |

Workflow source revision: `fb4df7ca18aa28fa9691a83175adb6928dac5c44`. The full and runtime images share their application/runtime layers; the complete image adds the verified model-cache layer.

The separate model image matched all 17 local cache files by SHA-256. Trackastra manifests and the pinned SAM2 backbone were verified before inference.

## Public-data matrix

| Case | Model | Selected label | Device / linking | Objects | Division events | Movies | Wall time |
| --- | --- | --- | --- | --- | --- | --- | --- |
| cuda-general_2d-0 | general_2d | instances | cuda / greedy | 138 | 0 | 0 | 17.2 s |
| cuda-general_2d-1 | general_2d | instances | cuda / greedy | 180 | 0 | 0 | 11.9 s |
| cuda-general_2d-2 | general_2d | instances | cuda / greedy | 36 | 0 | 0 | 11.6 s |
| cuda-ctc-0 | ctc | instances | cuda / greedy | 138 | 0 | 0 | 14.0 s |
| cuda-ctc-1 | ctc | instances | cuda / greedy | 180 | 0 | 0 | 12.3 s |
| cuda-ctc-2 | ctc | instances | cuda / greedy | 36 | 0 | 0 | 11.4 s |
| cuda-general_2d_w_SAM2_features-0 | general_2d_w_SAM2_features | instances | cuda / greedy | 138 | 0 | 2 | 31.5 s |
| cuda-general_2d_w_SAM2_features-1 | general_2d_w_SAM2_features | instances | cuda / greedy | 180 | 0 | 0 | 13.9 s |
| cuda-general_2d_w_SAM2_features-2 | general_2d_w_SAM2_features | instances | cuda / greedy | 36 | 0 | 0 | 12.7 s |
| cpu-no-divisions-movies | general_2d | instances | cpu / greedy_nodiv | 138 | 0 | 2 | 26.7 s |
| cpu-ilp | general_2d | instances | cpu / ilp | 138 | 0 | 0 | 13.2 s |
| cuda-long-divisions-movies | general_2d | instances | cuda / greedy | 2607 | 21 | 2 | 80.3 s |
| runtime-external-model-cache | general_2d | instances | cpu / greedy | 138 | 0 | 0 | 13.4 s |
| multi-label-default-first | general_2d | Nuclei | cuda / greedy | 180 | 0 | 0 | 12.7 s |
| multi-label-case-insensitive | general_2d | instances | cuda / greedy | 180 | 0 | 0 | 12.2 s |

All cases preserved source pixels and instance labels, passed SQLite integrity checks, matched CSV/table counts, verified calibrated coordinates and matched the database/NGFF output UUID. The external-cache case used the weight-free runtime with a read-only local model cache.

The short model matrix used six-frame GOWT1, SIM+ and U373 sequences. The longer movie case used 65 SIM+ frames and required predicted binary divisions. These calibrated CTC time series are wrapped as single-well, single-field test plates; they are compatibility checks and may overlap model training data. Counts are not biological accuracy scores.

The multi-label example preserves the original instance markers and adds the same geometry with IDs offset by 1000 as Nuclei. Its label registry deliberately lists Nuclei before instances. The two selection cases verify the default first label and an explicit mixed-case name, with exactly one field/label result each. This is a selection check, not new biological ground truth.

NGFF 0.4 / Zarr v2 remains required; NGFF 0.5 support is deferred. Production OMERO import, consumer plugin loading and Slurm/Apptainer submission remain deployment checks. Container validation does not establish that roundtrip.

See [machine-readable evidence](docker-validation.json), [Docker usage](docker.md), [dataset attribution](datasets.md) and the [release attachments](https://github.com/Cellular-Imaging-Amsterdam-UMC/citrackastra/releases/tag/v0.1.1).
