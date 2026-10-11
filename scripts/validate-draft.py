"""Local checks; this does not build the emulator or require Linux."""
import ast
import importlib.util
import json
from pathlib import Path
import struct
import sys
import tempfile

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / ".build-checks"))
import yaml

workflow = yaml.load((root / ".github/workflows/noble-arm64.yml").read_text(), Loader=yaml.BaseLoader)
assert "push" in workflow["on"] and "workflow_dispatch" in workflow["on"]
job = workflow["jobs"]["build"]
assert job["runs-on"] == "ubuntu-24.04-arm"
assert len(job["env"]["SOURCE_SHA"]) == 40
assert any(step.get("uses") == "actions/upload-artifact@v4" for step in job["steps"])
inline = root / ".validation"
inline.mkdir(exist_ok=True)
for index, step in enumerate(job["steps"]):
    if "run" in step:
        (inline / f"step-{index}.sh").write_text(step["run"], encoding="utf-8")
build = (root / "scripts/build.sh").read_text()
assert "set -euo pipefail" in build
assert "CMAKE_BUILD_TYPE=Release" in build
assert "march=armv8-a" in build
assert "mcpu=native" not in build
script = root / "scripts/package.py"
ast.parse(script.read_text())
spec = importlib.util.spec_from_file_location("packager", script)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
with tempfile.TemporaryDirectory(dir=inline) as tmp:
    path = Path(tmp) / "sample.elf"
    header = bytearray(20)
    header[:6] = b"\x7fELF\x02\x01"
    struct.pack_into("<H", header, 18, 183)
    path.write_bytes(header)
    module.require_arm64(path)
    struct.pack_into("<H", header, 18, 62)
    path.write_bytes(header)
    try:
        module.require_arm64(path)
    except RuntimeError:
        pass
    else:
        raise AssertionError("x86-64 ELF was incorrectly accepted")
for soname in ("libc.so.6", "libEGL.so.1", "libGLX_nvidia.so.0", "libvulkan.so.1"):
    assert module.HOST_LIBRARY.fullmatch(soname), soname
for soname in ("libQt6Core.so.6", "libstdc++.so.6", "libxcb.so.1"):
    assert not module.HOST_LIBRARY.fullmatch(soname), soname
print("PASS: workflow YAML, required build flags, Python syntax, ELF rejection and host graphics library policy.")
print("Inline shell files generated for bash -n. No emulator compilation was performed.")
