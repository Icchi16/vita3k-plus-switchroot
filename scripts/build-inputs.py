#!/usr/bin/env python3
"""Retain compiled files so packaging can be retried without rebuilding."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tarfile

root = Path(__file__).resolve().parent.parent
recipe_files = [root / "scripts/build.sh", root / "scripts/prepare-source.py"]
recipe_files += sorted((root / "patches").glob("*.patch"))
recipe = hashlib.sha256()
for file in recipe_files:
    recipe.update(file.relative_to(root).as_posix().encode() + b"\0" + file.read_bytes())
expected = {"source_sha": os.environ["SOURCE_SHA"], "qt_version": os.environ["QT_VERSION"],
            "recipe_sha256": recipe.hexdigest(), "configuration": "Release",
            "architecture": "AArch64", "cpu_baseline": "armv8-a"}
parser = argparse.ArgumentParser()
parser.add_argument("mode", choices=("save", "restore"))
args = parser.parse_args()
archive = root / "build-inputs.tar.gz"
build = root / "build"
if args.mode == "save":
    (build / "build-inputs.json").write_text(json.dumps(expected, indent=2))
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(build / "bin", arcname="bin")
        tar.add(build / "build-inputs.json", arcname="build-inputs.json")
else:
    if build.exists():
        raise RuntimeError("Refusing to restore into an existing build directory")
    with tarfile.open(archive, "r:gz") as tar:
        metadata = json.load(tar.extractfile("build-inputs.json"))
        if metadata != expected:
            raise RuntimeError(f"Build inputs do not match this source/recipe: {metadata}")
        for member in tar.getmembers():
            if member.name != "build-inputs.json" and not member.name.startswith("bin/") and member.name != "bin":
                raise RuntimeError(f"Unexpected build archive member: {member.name}")
        tar.extractall(build, filter="data")
print(f"{args.mode}: compiled inputs for {expected['source_sha']}")
