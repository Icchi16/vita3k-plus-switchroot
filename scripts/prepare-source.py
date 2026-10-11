#!/usr/bin/env python3
"""Supply build support missing from the pinned Plus checkout."""
from pathlib import Path
import os
import subprocess

root = Path(__file__).resolve().parent.parent
source = root / "source"
for directory, patch in (
    (source, root / "patches/cli-early-exit.patch"),
    (source / "external/LibAtrac9", root / "patches/libatrac9-bounded.patch"),
):
    subprocess.run(["git", "-C", str(directory), "apply", "--check", str(patch)], check=True)
    subprocess.run(["git", "-C", str(directory), "apply", str(patch)], check=True)

header = source / "vita3k/util/include/util/fork_build.h"
if header.exists():
    raise RuntimeError("Unexpected upstream fork_build.h; review build support first")
sequence = "noble-arm64-" + os.environ.get("GITHUB_RUN_NUMBER", "local")
if not all(char.isalnum() or char == "-" for char in sequence):
    raise RuntimeError("Invalid build sequence")
header.write_text(
    '#pragma once\n'
    '// Generated metadata for the Noble ARM64 build.\n'
    f'#define FORK_BUILD_SEQ "{sequence}"\n'
    '#define FORK_BUILD_CHANGES "Noble ARM64 build support"\n',
    encoding="utf-8",
)
print("Applied CLI early-exit fix, bounded Atrac9 API and generated build metadata.")
