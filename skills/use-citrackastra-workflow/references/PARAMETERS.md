# Parameters and output contract

Read the installed `config.yaml`; executable revision and runtime capabilities
take precedence over this reference when they differ. Report incompatibility
instead of guessing a replacement flag.

| Parameter | Default | Contract |
| --- | --- | --- |
| model | general_2d | general_2d, ctc, general_2d_w_SAM2_features; all support calibrated 2D timelapse images and plate fields |
| labels | empty | One optional case-insensitive NGFF label name. Empty selects the first registered label per field; registry-free legacy groups use alphabetical order. Missing/ambiguous names fail; `all` is literal. CLI: `--label` or `--labels`. |
| channel | 1 | One-based intensity channel, independent of the label channel |
| mode | greedy | greedy permits binary divisions; greedy_nodiv forbids divisions; ilp uses the installed solver stack |
| device | auto | auto/cuda/cpu/mps; request CUDA only when exposed by the workflow runtime |
| model_dir | models locally | Runtime normally supplies `/opt/models`. Models must already be cached and verified. |
| max_memory_gb | 4 | Estimated array working memory in GiB, not a hard process or GPU limit; graphs/models need extra memory |
| workers | 0 | Feature workers; zero uses the main process. Stay within allocated CPUs. |
| batch_size | 1 | Association prediction batch size |
| movie | false | Optional actual Divisualisation renderer; needs the movie runtime and a working OpenGL context |
| movie_fps | 12 | 1–60 playback frames/second; not the acquisition time interval |

All plate fields must pass preflight before inference. Spatial calibration is
read from NGFF metadata; OME-XML alone does not supply fallback calibration in
this adapter. Labels must match the source grid and units exactly. Unknown time
units produce frame-based motion; they do not prevent XY-calibrated tracking.

The optional SAM2 model also needs etultra/SAM2 packages and its cached SAM2.1
backbone. Missing optional dependencies must fail clearly. Do not download
models implicitly on compute nodes or rebuild images to recover a submitted job.

## Outputs

One `<plate>__citrackastra/` result directory per input:

- `<plate>__citrackastra.ome.zarr`: complete copied plate, original labels and
  `labels/<name>_tracks` in every processed field.
- `tracking.sqlite`: authoritative relational tracking data, schema version 1.
- `fields.csv`, `tracks.csv`, `observations.csv`, `links.csv`: queryable exports.
- `provenance.json`: complete status, versions, hashes and output UUID.
- Optional `tracking_movie.mp4`, `spacetime_movie.mp4` and `movie.json`: sequential field/label segments.

Check the installed integration's recursive output discovery and attach the
database/movie to the corresponding plate. Existing complete destinations are
refused. Hidden `.partial-*` directories with `FAILED.json` retain failure
evidence and must not be interpreted as completed output.

For table semantics load the companion `analyze-citrackastra-tracks` skill or
its `references/SCHEMA.md` resource. Numeric track IDs are local to each field
and label set. Movie playback FPS is separate from calibrated acquisition time.
