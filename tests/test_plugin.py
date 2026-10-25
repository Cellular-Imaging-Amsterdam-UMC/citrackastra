import json
from pathlib import Path

from bilayers_cli import generate_cli_command, load_config, validate_config
from citrackastra.cli import parser
from citrackastra.workflow import SCHEMA

ROOT = Path(__file__).resolve().parents[1]


def test_plugin_resources_resolve_and_database_match_is_schema_aware():
    import sqlite3
    manifest = json.loads((ROOT / "plugin.json").read_text(encoding="utf-8"))
    consumers = manifest["extensions"]["nl.bioimaging.biomero"]["skills"]
    for name, info in consumers.items():
        folder = ROOT / "skills" / name
        assert (folder / "SKILL.md").is_file()
        for resource in info["required_resources"]:
            assert (folder / resource).is_file()
    db = sqlite3.connect(":memory:")
    db.executescript(SCHEMA)
    required = consumers["analyze-citrackastra-tracks"]["match"]["required_tables"]
    actual = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert set(required) <= actual
    assert consumers["analyze-citrackastra-tracks"]["consumers"] == ["omero-analysis"]
    assert consumers["use-citrackastra-workflow"]["consumers"] == ["omero-biomero"]


def test_descriptor_generates_executable_cli_with_explicit_boolean_movie():
    import shlex
    config = load_config(ROOT / "config.yaml")
    assert validate_config(config) == []
    command = generate_cli_command(config, {"infolder": "plate in", "outfolder": "result out", "movie": True})
    args = parser().parse_args(shlex.split(command)[2:])
    assert args.infolder == "plate in" and args.outfolder == "result out"
    assert args.movie is True
    assert all(p["depth"] is False and p["timepoints"] is True for p in config["inputs"] if p["type"] == "image")
