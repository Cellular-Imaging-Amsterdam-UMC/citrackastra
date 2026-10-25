"""Optional isolated Divisualisation movie rendering."""

import json
import os
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path


def renderer_python():
    return os.environ.get("CITRACKASTRA_MOVIE_PYTHON", sys.executable)


def renderer_environment():
    env = os.environ.copy()
    source = str(Path(__file__).resolve().parents[1])
    env["PYTHONPATH"] = source + os.pathsep + env.get("PYTHONPATH", "")
    return env


def check_renderer():
    result = subprocess.run([renderer_python(), "-c", "import divisualisation, napari, imageio_ffmpeg; from qtpy.QtWidgets import QApplication"],
                            env=renderer_environment(), capture_output=True, text=True, timeout=60)
    if result.returncode:
        raise RuntimeError("Movie rendering needs the optional movie packages. Run install_movie.cmd or install .[movie]. " + result.stderr[-1500:])


def render_movie(stage, settings):
    command = [renderer_python(), "-m", "citrackastra.movie_renderer", str(Path(stage).resolve()), "--fps", str(settings.movie_fps), "--channel", str(settings.channel)]
    result = subprocess.run(command, env=renderer_environment(), capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError("Divisualisation movie rendering failed: " + result.stderr[-2500:])
    record = json.loads((Path(stage) / "movie.json").read_text(encoding="utf-8"))
    if not (Path(stage) / record["filename"]).is_file():
        raise RuntimeError("Renderer did not produce the requested movie")
    return record
