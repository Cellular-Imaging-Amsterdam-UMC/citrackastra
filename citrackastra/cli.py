"""Headless CLI shared by local use and Bilayers/BIOMERO."""

import argparse
import json
from dataclasses import fields

from .models import MODELS
from .workflow import Settings, run_workflow


def parser():
    p = argparse.ArgumentParser(description="CITrackastra: calibrated OME-Zarr instance tracking")
    p.add_argument("--infolder", "--input-dir", default="/data/in")
    p.add_argument("--outfolder", "--output-dir", default="/data/out")
    p.add_argument("--local", action="store_true", help="Compatibility flag; all inference uses local models")
    p.add_argument("--parameters", help="JSON object of workflow parameters")
    for field in fields(Settings):
        kwargs = {"type": type(field.default), "default": argparse.SUPPRESS}
        if isinstance(field.default, bool):
            kwargs.update(type=boolean, nargs="?", const=True)
        if field.name == "model":
            kwargs["choices"] = list(MODELS)
        p.add_argument("--" + field.name.replace("_", "-"), **kwargs)
    return p


def boolean(value):
    if isinstance(value, bool):
        return value
    if value.lower() in {"true", "1", "yes"}:
        return True
    if value.lower() in {"false", "0", "no"}:
        return False
    raise argparse.ArgumentTypeError("Expected true or false")


def main(argv=None):
    p = parser()
    args = p.parse_args(argv)
    try:
        values = json.loads(args.parameters) if args.parameters else {}
    except json.JSONDecodeError as exc:
        p.error(f"Invalid --parameters JSON: {exc.msg}")
    if not isinstance(values, dict):
        p.error("--parameters must be a JSON object")
    for field in fields(Settings):
        if hasattr(args, field.name):
            values[field.name] = getattr(args, field.name)
    try:
        run_workflow(args.infolder, args.outfolder, Settings(**values))
    except (ValueError, OSError, RuntimeError, TypeError, MemoryError) as exc:
        p.exit(1, f"CITrackastra failed: {exc}\n")
    return 0
