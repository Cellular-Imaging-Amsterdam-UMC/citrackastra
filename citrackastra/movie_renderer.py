"""Render one spacetime MP4 per plate, with sequential field/label segments.

This uses Divisualisation's actual SpacetimeLift engine. Ground-truth error
coloring is deliberately absent: ordinary workflow inputs contain no independently
matched reference lineage. The extra vertical coordinate represents time, not Z.
"""

import argparse
import json
import os
import sqlite3
import colorsys
import gc
from importlib.metadata import version
from pathlib import Path


def render(folder, fps, channel):
    # Windows needs the native WGL backend even for a hidden viewer. Linux can
    # use Xvfb + Mesa/GLX and xcb for unattended rendering.
    if os.name == "nt":
        os.environ.setdefault("QT_QPA_PLATFORM", "windows")
        os.environ.setdefault("QT_OPENGL", "desktop")
    os.environ.setdefault("NAPARI_ASYNC", "0")
    import imageio.v2 as imageio
    import napari
    import networkx as nx
    import numpy as np
    import zarr
    from divisualisation import SpacetimeLift
    from divisualisation.utils import graph_to_napari_tracks
    from PIL import Image, ImageDraw
    from qtpy.QtWidgets import QApplication
    from qtpy.QtCore import Qt

    from .ngff import inspect_image, sequence
    import dask
    dask.config.set(scheduler="synchronous")
    from napari.utils import resize_dask_cache
    resize_dask_cache(128 * 1024**2)

    folder = Path(folder)
    root = zarr.open_group(str(next(folder.glob("*.ome.zarr"))), mode="r", use_consolidated=False)
    output = folder / "spacetime_movie.mp4"
    tracking_output = folder / "tracking_movie.mp4"
    frames_written, tracking_frames, segments = 0, 0, []
    with sqlite3.connect(f"file:{(folder / 'tracking.sqlite').as_posix()}?mode=ro", uri=True) as db, imageio.get_writer(str(output), fps=fps, codec="libx264", pixelformat="yuv420p", macro_block_size=16) as writer, imageio.get_writer(str(tracking_output), fps=fps, codec="libx264", pixelformat="yuv420p", macro_block_size=16) as tracking_writer:
        fields = db.execute("SELECT field_id,image_path,source_label,output_label FROM fields ORDER BY field_id").fetchall()
        for field_id, path, source_label, output_label in fields:
            group = root[path] if path else root
            info = inspect_image(group)
            imgs = sequence(group, info, channel, lazy=True)
            masks = sequence(group[f"labels/{output_label}"], info, lazy=True)
            # Display-only normalization uses a bounded sample shared across time.
            stride = max(1, int(np.ceil((imgs.size / 1_000_000) ** (1 / 3))))
            lo, hi = np.percentile(np.asarray(imgs[::stride, ::stride, ::stride]), [1, 99.8])
            display = np.clip((imgs.astype("f4") - lo) / max(float(hi - lo), 1e-9), 0, 1)
            graph = nx.DiGraph()
            for t, value, y, x in db.execute("SELECT timepoint,source_label,y_px,x_px FROM observations WHERE field_id=?", (field_id,)):
                graph.add_node((t, value), t=t, y=y, x=x)
            for a, b, c, d in db.execute("SELECT source_frame,source_label,target_frame,target_label FROM links WHERE field_id=?", (field_id,)):
                graph.add_edge((a, b), (c, d))
            # A conventional 2D tracking movie complements the actual lifted view.
            from PIL import ImageOps
            point_rows = db.execute("SELECT track_id,timepoint,y_px,x_px FROM observations WHERE field_id=? ORDER BY timepoint", (field_id,)).fetchall()
            paths = {}
            for track_id, t, y, x in point_rows:
                paths.setdefault(track_id, []).append((t, y, x))
            parents = {int(track): int(parent) for track, parent in db.execute("SELECT track_id,parent_track_id FROM tracks WHERE field_id=? AND parent_kind='division'", (field_id,))}
            event_frames = {int(row[0]) for row in db.execute("SELECT DISTINCT target_frame FROM links WHERE field_id=? AND kind='division'", (field_id,))}
            colors = {track_id: tuple(int(v * 255) for v in colorsys.hsv_to_rgb((track_id * .618034) % 1, .7, 1)) for track_id in paths}
            tracking_start = tracking_frames
            print(f"Rendering 2D tracking movie: {len(imgs)} timepoints", flush=True)
            for t, plane in enumerate(display):
                plane = np.asarray(plane)
                frame_image = Image.fromarray((plane * 255).astype("u1")).convert("RGB")
                drawing = ImageDraw.Draw(frame_image)
                for track_id, points in paths.items():
                    visible = [(x, y) for frame, y, x in points if max(0, t - 12) <= frame <= t]
                    if len(visible) > 1:
                        drawing.line(visible, fill=colors[track_id], width=2)
                    current = next(((y, x) for frame, y, x in points if frame == t), None)
                    if current:
                        y, x = current
                        drawing.ellipse((x - 3, y - 3, x + 3, y + 3), outline=colors[track_id], width=2)
                        drawing.text((x + 4, y - 5), str(track_id), fill=colors[track_id])
                        if track_id in parents and t - points[0][0] <= 3:
                            parent_point = paths[parents[track_id]][-1]
                            drawing.line([(parent_point[2], parent_point[1]), (x, y)], fill=(255, 130, 190), width=3)
                fitted = ImageOps.contain(frame_image, (940, 640))
                frame = Image.new("RGB", (960, 720), (8, 12, 14))
                frame.paste(fitted, ((960 - fitted.width) // 2, 70 + (640 - fitted.height) // 2))
                drawing = ImageDraw.Draw(frame)
                drawing.text((16, 12), f"CITrackastra | Field {path} | {source_label} | Frame {t}/{len(imgs) - 1}", fill="white")
                event = " | PREDICTED CELL DIVISION" if any(0 <= t - event <= 3 for event in event_frames) else ""
                drawing.text((16, 34), f"2D source + predicted trajectories | XY: {info.scale[-2]:g}, {info.scale[-1]:g} um/pixel{event}", fill=(239, 164, 195))
                for _ in range(max(1, fps // 4)):
                    tracking_writer.append_data(np.asarray(frame))
                    tracking_frames += 1
            print("Preparing spacetime viewer", flush=True)
            viewer = napari.Viewer(show=False)
            viewer.window._qt_window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
            viewer.window._qt_window.resize(1100, 850)
            viewer.show()
            lift = None
            try:
                viewer.theme = "dark"
                viewer.add_image(display, name="Source", colormap="gray", contrast_limits=(0, 1), scale=(1, *info.scale), cache=False)
                viewer.add_labels(masks, name="Predicted trajectory masks", opacity=.20, scale=(1, *info.scale), cache=False)
                if graph.number_of_nodes():
                    tracks, parents, _ = graph_to_napari_tracks(graph, include_z=False, drop_division_duplicates=False)
                    layer = viewer.add_tracks(tracks, graph=parents, name="Predicted tracks", tail_length=len(imgs), scale=(1, *info.scale))
                    layer.display_graph = False
                    lift_scale = max(imgs.shape[-2] * info.scale[-2], imgs.shape[-1] * info.scale[-1]) * .45 / max(1, len(imgs) - 1)
                    lift = SpacetimeLift(viewer, lift_scale=float(lift_scale))
                    print("Applying spacetime lift", flush=True)
                    lift.apply({"pred": "Predicted tracks"})
                viewer.reset_view()
                if lift:
                    viewer.camera.angles = (-15, -2, -65)
                    viewer.camera.perspective = 35
                    viewer.camera.zoom *= .8
                application = QApplication.instance()
                sweep = np.linspace(0, len(imgs) - 1, max(len(imgs), fps * 3)).astype(int).tolist()
                timeline = sweep + [len(imgs) - 1] * fps + list(reversed(sweep))
                segment_start = frames_written
                print(f"Rendering spacetime movie: {len(timeline)} frames", flush=True)
                for frame_index, t in enumerate(timeline):
                    viewer.dims.set_current_step(0, int(t))
                    application.processEvents()
                    screenshot = viewer.screenshot(canvas_only=True, flash=False)
                    if np.std(screenshot[..., :3]) < 1:
                        raise RuntimeError("The OpenGL renderer returned a blank frame")
                    frame = Image.fromarray(screenshot[..., :3]).resize((960, 720))
                    draw = ImageDraw.Draw(frame)
                    draw.rectangle((0, 0, 960, 60), fill=(15, 20, 23))
                    draw.text((16, 10), f"CITrackastra / Divisualisation | Field {path} | {source_label} | Frame {t}", fill="white")
                    draw.text((16, 32), f"2D+t spacetime view: vertical axis = time, not physical Z. XY: {info.scale[-2]:g}, {info.scale[-1]:g} um/pixel", fill=(239, 164, 195))
                    writer.append_data(np.asarray(frame))
                    frames_written += 1
                    if frame_index % 25 == 0:
                        gc.collect()
                        print(f"Spacetime frame {frame_index + 1}/{len(timeline)}", flush=True)
                segments.append({"field_id": field_id, "image_path": path, "source_label": source_label, "start_movie_frame": segment_start, "end_movie_frame": frames_written - 1, "tracking_start_frame": tracking_start, "tracking_end_frame": tracking_frames - 1, "predicted_division_frames": sorted(event_frames)})
            finally:
                # This viewer is disposable. Reverting the lift first changes
                # image/label ndim while the viewer still displays 3D, causing
                # napari to materialize the entire time series as a volume.
                viewer.close()
    if not frames_written or output.stat().st_size == 0:
        raise RuntimeError("No movie frames were rendered")
    record = {"filename": output.name, "tracking_filename": tracking_output.name, "tracking_frames": tracking_frames, "renderer": "Divisualisation SpacetimeLift + napari; Pillow for conventional 2D view", "divisualisation_version": version("divisualisation"),
              "napari_version": version("napari"), "fps": fps, "frames": frames_written, "size": [960, 720], "segments": segments,
              "ground_truth_errors": False, "interpretation": "Predictions only. Time is lifted into a display axis; it is not physical Z. Fields and label sets play sequentially."}
    (folder / "movie.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    parser.add_argument("--fps", type=int, default=12)
    parser.add_argument("--channel", type=int, default=1)
    args = parser.parse_args()
    render(args.folder, args.fps, args.channel)
