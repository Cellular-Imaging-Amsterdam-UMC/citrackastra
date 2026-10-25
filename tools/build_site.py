"""Build English documentation and an interactive gallery of actual model results."""

import argparse
import html
import json
import sqlite3
import shutil
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
REPO = "https://github.com/Cellular-Imaging-Amsterdam-UMC/citrackastra"


def gallery(report):
    import numpy as np
    import zarr
    from PIL import Image

    (DOCS / "gallery").mkdir(exist_ok=True)
    samples = []
    for run in sorted(report.get("runs", []), key=lambda r: (-(r["source"]["frame_range"][1] + 1), r["dataset"])):
        if run["model"] != "general_2d" or run["mode"] != "greedy":
            continue
        folder = Path(run["result"])
        root = zarr.open_group(str(next(folder.glob("*.ome.zarr"))), mode="r")
        data = root["A/1/0/0"][:, 0, 0]
        lo, hi = np.percentile(data, [1, 99.8])
        images = []
        for t, plane in enumerate(data):
            display = np.clip((plane.astype(float) - lo) / max(hi - lo, 1e-9) * 255, 0, 255).astype("u1")
            image = Image.fromarray(display)
            image.thumbnail((640, 640))
            name = f"gallery/{run['dataset'].removesuffix('.ome.zarr')}-{t}.webp"
            image.save(DOCS / name, quality=90)
            images.append(name)
        with sqlite3.connect(folder / "tracking.sqlite") as db:
            points = db.execute("SELECT track_id,timepoint,y_px,x_px FROM observations ORDER BY track_id,timepoint").fetchall()
        tracks = {}
        for track, t, y, x in points:
            tracks.setdefault(str(track), []).append([t, x / data.shape[2], y / data.shape[1]])
        movie, tracking_movie = None, None
        if (folder / "movie.json").is_file():
            movie_info = json.loads((folder / "movie.json").read_text(encoding="utf-8"))
            movie = f"gallery/{run['dataset'].removesuffix('.ome.zarr')}-spacetime.mp4"
            shutil.copyfile(folder / movie_info["filename"], DOCS / movie)
            if movie_info.get("tracking_filename"):
                tracking_movie = f"gallery/{run['dataset'].removesuffix('.ome.zarr')}-tracking.mp4"
                shutil.copyfile(folder / movie_info["tracking_filename"], DOCS / tracking_movie)
        name = re.sub(r"-01-\d+frames\.ome\.zarr$", "", run["dataset"]) + f" ({len(data)} frames)"
        samples.append({"name": name, "images": images, "movie": movie, "tracking_movie": tracking_movie,
                        "tracks": tracks, "source": run["source"], "counts": run["counts"], "runtime_seconds": run["runtime_seconds"]})
    (DOCS / "assets/examples.json").write_text(json.dumps({"samples": samples}, indent=2), encoding="utf-8")
    return samples


def page(filename, title, body):
    links = ''.join(f'<a href="{name}"' + (' aria-current="page"' if name == filename else '') + f'>{label}</a>' for name, label in [("index.html", "Overview"), ("workflow.html", "Workflow"), ("examples.html", "Examples"), ("validation.html", "Validation")])
    text = f'''<!doctype html><html lang="en" data-theme="dark"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="Calibrated OME-Zarr cell tracking with Trackastra, Bilayers and BIOMERO."><title>{title} Â· CITrackastra</title><script src="assets/theme.js"></script><link rel="stylesheet" href="assets/style.css"><link rel="stylesheet" href="assets/themes.css"><link rel="stylesheet" href="assets/tracking.css"><script src="assets/site.js" defer></script></head><body><a class="skip" href="#main">Skip to content</a><header class="topbar"><div class="shell nav"><a class="brand" href="index.html"><svg viewBox="0 0 40 40" fill="none" aria-hidden="true"><rect x="2" y="2" width="36" height="36" rx="10" stroke="currentColor"/><path d="M10 29L19 20L29 12M19 20L30 29" stroke="#efa4c3" stroke-width="2"/><circle cx="10" cy="29" r="3" fill="#9bc8b5"/><circle cx="19" cy="20" r="3" fill="#efa4c3"/><circle cx="29" cy="12" r="3" fill="#9bc8b5"/><circle cx="30" cy="29" r="3" fill="#9bc8b5"/></svg>CITrackastra</a><nav class="navlinks" aria-label="Main navigation">{links}<button type="button" class="theme-toggle" data-theme-toggle aria-label="Theme: Dark. Switch to Bright" aria-pressed="true"><span class="theme-bright">Bright</span><span class="theme-dark">Dark</span></button><a class="repo" href="{REPO}">GitHub â†—</a></nav></div></header><main class="shell" id="main">{body}</main><footer class="footer"><div class="shell footer-row"><span>Cellular Imaging Â· Amsterdam UMC</span><span>CITrackastra 0.1.0 Â· Trackastra 0.5.6</span><a href="{REPO}/blob/main/NOTICE.md">Sources &amp; licenses â†—</a></div></footer></body></html>'''
    (DOCS / filename).write_text(text, encoding="utf-8")


def build(report):
    samples = gallery(report)
    hero = f'<img src="{samples[0]["images"][-1]}" alt="Fluorescent mouse stem-cell nuclei from the calibrated GOWT1 public dataset">' if samples else '<div class="schematic">instances â†’ associations â†’ trajectories</div>'
    page("index.html", "From instances to cell histories", f'''
<section class="hero"><div><div class="eyebrow">OME-Zarr Â· Bilayers Â· BIOMERO</div><h1>From instances<br>to <em>cell</em><br>histories.</h1><p>Connect segmented cells across time. CITrackastra brings transformer-based tracking to calibrated microscopy images, with traceable trajectories and physical measurements.</p><div class="actions"><a class="button primary" href="examples.html">Explore actual trajectories â†—</a><a class="button" href="workflow.html#getting-started">Get started locally</a></div><p class="fine">Powered by Trackastra Â· local pretrained weights Â· research workflow</p></div><div class="hero-visual">{hero}<div class="visual-caption"><span>CALIBRATED INPUT. TRACEABLE OUTPUT.</span><span>PUBLIC MICROSCOPY</span></div></div></section>
<div class="stats"><div><strong>3</strong><span>upstream pretrained model variants</span></div><div><strong>2D + time</strong><span>calibrated HCS plates only</span></div><div><strong>Âµm</strong><span>calibrated coordinates and motion</span></div><div><strong>Offline</strong><span>explicit local model cache</span></div></div>
<section class="section"><div class="section-head"><div><div class="eyebrow">From labels to lineages</div><h2>Keep the biology.<br>Connect the timepoints.</h2></div><p>Segment first with CISegmentation or another instance model. Trackastra predicts associations; CITrackastra preserves source pixels and records every link.</p></div><div class="steps"><div class="step"><span class="number">01 / INPUT</span><h3>Bring your instances</h3><p>OME-Zarr HCS plates with 2D time series and matching labels. Every field is checked independently.</p></div><div class="step"><span class="number">02 / CALIBRATION</span><h3>Require physical units</h3><p>Positive XY sizes and matching labels in every field. Volumes and static plates are rejected.</p></div><div class="step"><span class="number">03 / ASSOCIATION</span><h3>Predict the links</h3><p>General 2D, CTC or SAM2 features. Greedy linking with or without divisions, or ILP optimization.</p></div><div class="step"><span class="number">04 / OUTPUT</span><h3>Inspect cell histories</h3><p>Additional trajectory labels, SQLite and CSV tables, source IDs and model provenance.</p></div></div></section>
<section class="section"><div class="section-head"><div><div class="eyebrow">Open evidence</div><h2>See the predictions.<br>Know their limits.</h2></div><p>The gallery uses actual predictions on public, physically calibrated data. Reference markers are inputs for smoke validation; this is not a segmentation benchmark.</p></div><div class="feature-links"><a class="feature-card" href="examples.html"><small>01 / Gallery</small><h3>Play through real trajectories â†—</h3><p>Move through short and full-length sequences, inspect source images and follow predicted paths.</p></a><a class="feature-card" href="workflow.html"><small>02 / Usage</small><h3>One headless workflow â†—</h3><p>Local CLI, NVIDIA CUDA, cached models and Bilayers/BIOMERO integration.</p></a><a class="feature-card" href="validation.html"><small>03 / Evidence</small><h3>Validation and limitations â†—</h3><p>Test coverage, actual device runs, calibration sources and deployment status.</p></a></div></section>
<section class="section split"><div><div class="eyebrow">Getting started</div><h2>Begin locally.</h2><p>Download all three tracking checkpoints and the SAM2 backbone once, then infer from the local cache.</p><a class="button" href="workflow.html#getting-started">Installation and commands â†—</a></div><div><pre><code>git clone {REPO}.git
cd citrackastra
create_env.cmd
install_cuda.cmd
.venv\\Scripts\\python tools\\download_models.py</code></pre><p class="fine">Python 3.11 Â· CPU or NVIDIA CUDA Â· Docker recipes prepared separately.</p></div></section>''')
    page("workflow.html", "Workflow and local setup", '''<section class="page-head"><div class="eyebrow">Workflow</div><h1>From your labels<br>to <em>linked</em> objects.</h1><p>A headless workflow for local runs and Bilayers/BIOMERO.</p></section><article class="prose"><h2 id="getting-started">Install locally</h2><pre><code>create_env.cmd
install_cuda.cmd
.venv\\Scripts\\python tools\\download_models.py
.venv\\Scripts\\python tools\\prepare_publicdata.py
.venv\\Scripts\\python wrapper.py --local --infolder publicdata/plates \\
  --outfolder outputfolder --device cuda --model general_2d</code></pre>
<p>Setup requires uv and creates Python 3.11. CUDA setup installs matching PyTorch 2.11.0 and torchvision 0.26.0 wheels with CUDA 12.6. Use <code>--device cpu</code> for CPU inference. Run <code>install_sam2.cmd</code> before selecting the optional SAM2 model.</p>
<h2>Input contract</h2><p>Use NGFF 0.4 / Zarr v2 directories with explicit t/y/x axes, optional c/z, positive spatial scales and physical spatial units. The root must declare a plate and wells with listed image fields. Each field needs at least two frames, Z absent or singleton, and instance labels on the same grid. Labels must match image dimensions, transforms and units. Channel numbers are one-based. Calibration must be in NGFF; an OME-XML file alone is insufficient for this adapter.</p><p>Only HCS plates with 2D time series are accepted. Standalone images, static fields and volumes are rejected; nothing is projected. Use CISegmentation outputs with <code>--labels labels_cells</code> or another label group. Source stores are read-only. Materialize labels-only overlays with corresponding source pixels before use.</p>
<h2>Pretrained models</h2><table><thead><tr><th>Model</th><th>Dimensions</th><th>Requirements</th></tr></thead><tbody><tr><td>general_2d</td><td>2D</td><td>General-purpose association transformer</td></tr><tr><td>ctc</td><td>2D plate fields</td><td>CTC association model</td></tr><tr><td>general_2d_w_SAM2_features</td><td>2D</td><td>Optional etultra/SAM2 packages and cached SAM2.1 backbone</td></tr></tbody></table>
<h2>Parameters</h2><table><thead><tr><th>Flag</th><th>Default</th><th>Meaning</th></tr></thead><tbody><tr><td>--labels</td><td>all</td><td>All label groups or comma-separated names</td></tr><tr><td>--channel</td><td>1</td><td>One image channel for association features</td></tr><tr><td>--mode</td><td>greedy</td><td>greedy, greedy_nodiv or ilp</td></tr><tr><td>--device</td><td>auto</td><td>auto, cuda, cpu or mps</td></tr><tr><td>--model-dir</td><td>models</td><td>Local verified cache</td></tr><tr><td>--max-memory-gb</td><td>4</td><td>Array preflight in GiB; graph/model costs are additional</td></tr><tr><td>--workers</td><td>0</td><td>Feature workers; zero uses the main process</td></tr><tr><td>--batch-size</td><td>1</td><td>Prediction batch size</td></tr><tr><td>--movie</td><td>false</td><td>2D tracking and Divisualisation MP4s per plate; optional runtime required</td></tr><tr><td>--movie-fps</td><td>12</td><td>Playback rate, separate from acquisition time</td></tr></tbody></table>
<h2>Output semantics</h2><p>Each source publishes a result directory with its copied OME-Zarr, <code>tracking.sqlite</code>, <code>fields.csv</code>, <code>tracks.csv</code>, <code>observations.csv</code>, <code>links.csv</code> and <code>provenance.json</code>. Trajectory labels live under <code>labels/&lt;source_name&gt;_tracks</code>. Optional <code>tracking_movie.mp4</code>, <code>spacetime_movie.mp4</code> and <code>movie.json</code> contain sequential Divisualisation spacetime segments per field and label set. The vertical display axis is time, not physical Z; no independent error scoring is implied. Original pixels and labels are preserved. Existing destinations cannot be overwritten. Failures retain a hidden partial directory and <code>FAILED.json</code>.</p><p>Join using <code>field_id</code> and <code>track_id</code>. IDs identify CTC tracklets: gaps and divisions start new segments. <code>parent_kind</code> distinguishes gap continuation from division. Observations retain original instance IDs. Coordinates apply ordered transforms in micrometers; speed uses micrometers per second with calibrated time, otherwise per frame. Singleton speeds are NULL. Inference uses the original pixel grid; output calibration does not resample anisotropic voxels.</p>
<h2>Bilayers and BIOMERO</h2><p><code>config.yaml</code> follows the CISegmentation descriptor pattern. <code>python bilayers_cli.py validate</code> checks the descriptor; <code>generate</code> prints its command. Stage images at <code>/data/in</code>, outputs at <code>/data/out</code> and cached models at <code>/opt/models</code>. The descriptor image is a planned release target.</p><p>Result stores live one level inside each source result directory. The integration must discover stores recursively and attach their SQLite/CSV companions. Verify this mapping in your installed BIOMERO version. Production OMERO/Slurm roundtrip validation has not been performed.</p>
<h2>Divisualisation movie</h2><p>Install <code>install_movie.cmd</code> and add <code>--movie true</code>. This uses the actual <a href="https://github.com/bentaculum/divisualisation/">Divisualisation SpacetimeLift</a> renderer, with a conventional 2D tracking MP4 and a spacetime MP4 per plate. Plate fields and label sets play as sequential segments. Windows uses a hidden native OpenGL context; unattended Linux uses the prepared Xvfb/Mesa movie runtime.</p><h2>Separate model images</h2><p><code>Dockerfile</code> prepares the headless CUDA runtime. <code>Dockerfile.models</code> packages only the cached models and licenses; <code>Dockerfile.with-models</code> combines them later. Alternatively bind-mount the cache at <code>/opt/models</code>. <code>Dockerfile.movie</code> adds the optional unattended movie runtime. No Docker build or Docker Hub publication has been performed.</p>
<h2>Cite the method</h2><p>Benjamin Gallusser and Martin Weigert, <a href="https://www.ecva.net/papers/eccv_2024/papers_ECCV/papers/09819.pdf">Trackastra: Transformer-based cell tracking for live-cell microscopy</a>, ECCV 2024. Cite SAM2 and Trackastra-et-Ultra when using SAM2 features. See NOTICE for sources and licenses.</p></article>''')
    cards = []
    for index, sample in enumerate(samples):
        source = sample["source"]
        cards.append(f'''<article class="sample"><div class="sample-body"><div class="eyebrow">ACTUAL MODEL PREDICTION</div><h2>{html.escape(sample['name'])}</h2><p>{html.escape(source['description'])} Â· {source['pixel_um']} Âµm/pixel Â· {source['seconds_per_frame']} s/frame.</p><div class="track-viewer" data-sample="{index}"><img src="{sample['images'][0]}" alt="Source microscopy frame with predicted centroid trajectories"><svg viewBox="0 0 1000 1000" preserveAspectRatio="none" aria-label="Predicted object trajectories"></svg></div><div class="play-controls"><button class="button" type="button" data-play="{index}">Play</button><label>Frame <output id="frame-{index}">0</output><input type="range" min="0" max="{len(sample['images']) - 1}" value="0" step="1" data-frame="{index}" aria-label="Frame for {html.escape(sample['name'])}"></label></div><p class="fine">Display: shared 1â€“99.8 percentile stretch. Paths: actual <code>general_2d / greedy</code> predictions. Input labels are CTC TRA reference markers, which may be smaller than full cells or nuclei.</p><p>{sample['counts']['observations']} observations Â· {sample['counts']['tracks']} tracklets Â· {sample['counts']['links']} links. <a href="https://zenodo.org/records/{source['zenodo_record']}">Dataset &amp; attribution â†—</a> Â· CC BY 4.0.</p></div></article>''')
    for index, sample in enumerate(samples):
        if sample.get("movie"):
            video = f'<p>Divisualisation spacetime movie: the vertical display axis is time.</p><video controls preload="metadata" width="960" poster="{sample["images"][0]}"><source src="{sample["movie"]}" type="video/mp4">Your browser does not support MP4 playback.</video>'
            if sample.get("tracking_movie"):
                video = f'<p>Conventional 2D tracking movie with IDs and predicted division events.</p><video controls preload="metadata" width="960" poster="{sample["images"][0]}"><source src="{sample["tracking_movie"]}" type="video/mp4">Your browser does not support MP4 playback.</video>' + video
            reference_events = sample["source"].get("reference_divisions", [])
            if len(sample["images"]) > 6:
                predicted = sample["counts"].get("divisions", 0)
                video = f'<p><strong>Longer division example:</strong> {len(sample["images"])} source frames; {len(reference_events)} documented binary reference divisions and predicted division events: {predicted}. Counts alone are not an accuracy score.</p>' + video
            cards[index] = cards[index].replace('</div></article>', video + '</div></article>')
    page("examples.html", "Actual tracking examples", '''<section class="page-head"><div class="eyebrow">Public microscopy Â· actual predictions</div><h1>Follow objects<br><em>through</em> time.</h1><p>Inspect predicted centroid paths on calibrated public data. Short and full-length examples verify the workflow; they do not establish biological accuracy.</p></section><div class="tracking-gallery">''' + ''.join(cards) + '''</div><section class="section prose"><h2>Read the examples correctly</h2><p>Source frames and reference markers are preserved. These original time series are packaged as single-well, single-field NGFF test plates. Their physical acquisition calibration is retained. The model uses intensities and object geometry; reference IDs are not association scores. CTC training data may overlap pretrained-model training. No independent generalization or segmentation accuracy is claimed. Synthetic integration tests separately exercise HCS isolation, divisions, gaps and rejection of unsupported inputs.</p><p>Calibration comes from <a href="https://celltrackingchallenge.net/2d-datasets/">CTC acquisition descriptions</a>. Original TIFF archives, checksums and converted OME-Zarr stores remain local, outside Git. This site distributes derived display frames, predicted centroid paths and review movies, attributed to the CTC datasets under CC BY 4.0.</p></section>''')
    rows = ''.join(f'<tr><td>{html.escape(r["dataset"].removesuffix("-01-6frames.ome.zarr"))}</td><td>{html.escape(r["model"])}</td><td>{html.escape(r["mode"])}</td><td>{r["counts"]["observations"]}</td><td>{r["runtime_seconds"]:.2f} s</td><td>{r.get("peak_cuda_allocated_mib", 0) or 0:.0f} MiB</td><td>Passed</td></tr>' for r in report.get("runs", []))
    evidence = f'<p>Recorded device: <strong>{html.escape(report.get("device", "Pending"))}</strong>. PyTorch {html.escape(report.get("torch", "pending"))}; CUDA runtime {html.escape(str(report.get("cuda_runtime", "pending")))}.</p>'
    page("validation.html", "Validation and limitations", '''<section class="page-head"><div class="eyebrow">Evidence and limitations</div><h1>Test the workflow.<br><em>Review</em> the biology.</h1><p>Execution, file compatibility and biological accuracy are separate questions.</p></section><article class="prose"><h2>Local model runs</h2>''' + evidence + '<div class="table-scroll"><table><thead><tr><th>Dataset</th><th>Model</th><th>Mode</th><th>Objects</th><th>Runtime</th><th>Peak GPU allocation</th><th>Result</th></tr></thead><tbody>' + rows + '''</tbody></table></div><p>Each listed run loaded verified local weights. Validation compares output pixels and original labels with input, checks SQLite integrity and retains model/dataset hashes. Tracking-stage runtime includes copying, inference and table preparation; movie rendering and final export are excluded. GPU figures are PyTorch peak allocation, not total device usage.</p><h2>Automated coverage</h2><p>Axis reordering, anisotropic coordinates, ordered transforms, calibration rejection, mismatched grids, HCS isolation, source preservation, overwrite refusal, memory guards, CLI types, checkpoint integrity, gaps, divisions, empty inputs and failed-run publication are tested. See <a href="https://github.com/Cellular-Imaging-Amsterdam-UMC/citrackastra/actions">GitHub Actions</a> and the <a href="https://github.com/Cellular-Imaging-Amsterdam-UMC/citrackastra/blob/main/docs/validation.md">local validation record</a>.</p><h2>Practical limits</h2><ul><li>Sequence inference is in memory. Graph and model costs depend on object density; this is not a gigapixel streaming tracker.</li><li>Inference uses the original pixel grid. Physical calibration does not compensate the model input for anisotropic sampling.</li><li>Reference-marker tests and training overlap do not establish segmentation accuracy or independent generalization.</li><li>Multi-field isolation has synthetic integration coverage. The public time series are single-field test-plate wrappers, not original multiwell screens.</li><li>Divisions and ambiguous crossings need review. Tracklets split at divisions and gaps; inspect parent_kind and links.</li><li>Docker recipes and the Bilayers descriptor are prepared. Docker publication and production OMERO/Slurm validation have not been performed.</li></ul><h2>Reproduce</h2><pre><code>test.cmd
.venv\\Scripts\\python tools\\prepare_publicdata.py
.venv\\Scripts\\python tools\\validate_local.py --device cuda
.venv\\Scripts\\python tools\\build_site.py --validation test-results/public/validation.json
.venv\\Scripts\\python tools\\check_site.py docs</code></pre></article>''')


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validation", type=Path)
    args = parser.parse_args()
    build(json.loads(args.validation.read_text(encoding="utf-8")) if args.validation else {})
