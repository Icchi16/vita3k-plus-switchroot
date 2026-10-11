#!/usr/bin/env python3
"""Package an already-built Linux AArch64 executable and its runtime dependencies."""
import argparse
import collections
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tarfile
import tempfile

# Keep the host's glibc and graphics driver/loader stack. Switchroot supplies Tegra.
HOST_LIBRARY = re.compile(
    r"^(ld-linux.*|lib(c|m|dl|pthread|rt|resolv|util|anl|nss_[^.]+)\.so.*|"
    r"lib(GL|EGL.*|GLES.*|GLX.*|OpenGL|GLdispatch|vulkan|drm.*|gbm|glapi|nvidia.*|cuda)\.so.*)$"
)
PLUGIN_GROUPS = (
    "platforms", "platforminputcontexts", "imageformats", "iconengines",
    "tls", "multimedia", "xcbglintegrations", "egldeviceintegrations",
    "wayland-decoration-client", "wayland-graphics-integration-client",
    "wayland-shell-integration",
)

def run(argv, **kwargs):
    return subprocess.run(argv, check=True, text=True, capture_output=True, **kwargs)

def require_arm64(path):
    with Path(path).open("rb") as elf:
        header = elf.read(20)
    if len(header) < 20 or header[:6] != b"\x7fELF\x02\x01":
        raise RuntimeError(f"Expected ELF64 little-endian: {path}")
    if struct.unpack_from("<H", header, 18)[0] != 183:
        raise RuntimeError(f"Expected AArch64 machine: {path}")

def dependencies(path, env):
    result = run(["ldd", str(path)], env=env)
    missing = [line.strip() for line in result.stdout.splitlines() if "not found" in line]
    if missing:
        raise RuntimeError(f"Unresolved dependencies for {path}: {missing}")
    found = []
    for line in result.stdout.splitlines():
        match = re.match(r"\s*(\S+)\s+=>\s+(/\S+)", line)
        if match:
            found.append((match.group(1), Path(match.group(2))))
    return found

def make_package(args):
    binary = args.binary.resolve()
    qt = args.qt.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    name = "Vita3K-Plus-Noble-ARM64"
    root = output / name
    root.mkdir()  # Refuse to mix new output with an old package.
    lib = root / "lib"
    lib.mkdir()
    licenses = root / "licenses"
    licenses.mkdir()
    require_arm64(binary)
    shutil.copy2(binary, root / "Vita3K")
    for name in ("data", "translations", "shaders-builtin", "icons"):
        source_dir = binary.parent / name
        if not source_dir.is_dir():
            raise RuntimeError(f"Build resources missing: {source_dir}")
        shutil.copytree(source_dir, root / name)
    shutil.copy2(args.source / "COPYING.txt", licenses / "Vita3K-COPYING.txt")
    license_source = Path(__file__).resolve().parent.parent / "licenses"
    if license_source.is_dir():
        shutil.copytree(license_source, licenses / "Qt-license-texts")
    build_support = Path(__file__).resolve().parent.parent
    shutil.copytree(build_support / "patches", root / "build-support/patches")
    shutil.copy2(build_support / "scripts/prepare-source.py", root / "build-support/prepare-source.py")

    plugin_root = root / "plugins"
    for group in PLUGIN_GROUPS:
        folder = qt / "plugins" / group
        if folder.is_dir():
            shutil.copytree(folder, plugin_root / group)
    for required in ("libqxcb.so", "libqoffscreen.so"):
        if not (plugin_root / "platforms" / required).is_file():
            raise RuntimeError(f"Required Qt platform plugin missing: {required}")
    for folder_name in ("Licenses", "licenses", "LICENSES"):
        folder = qt / folder_name
        if folder.is_dir():
            shutil.copytree(folder, licenses / ("Qt-" + folder_name))

    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = str(qt / "lib") + ":" + str(binary.parent)
    initial_elfs = [root / "Vita3K"] + sorted(plugin_root.rglob("*.so"))
    # Resolve against original locations. Partially copied $ORIGIN dependencies
    # would otherwise resolve back into lib/ and look like conflicting inputs.
    dependency_inputs = [binary] + [qt / "plugins" / obj.relative_to(plugin_root)
                                  for obj in initial_elfs[1:]]
    queue = collections.deque(dependency_inputs)
    copied = {}
    host_libraries = set()
    while queue:
        obj = queue.popleft()
        require_arm64(obj)
        for soname, resolved in dependencies(obj, env):
            if HOST_LIBRARY.fullmatch(soname):
                host_libraries.add(soname)
                continue
            resolved = resolved.resolve()
            if soname in copied:
                if copied[soname] != str(resolved):
                    previous = Path(copied[soname])
                    if hashlib.sha256(previous.read_bytes()).digest() != hashlib.sha256(resolved.read_bytes()).digest():
                        raise RuntimeError(f"Different libraries have the same SONAME: {soname}: {previous} and {resolved}")
                continue
            require_arm64(resolved)
            destination = lib / soname
            shutil.copy2(resolved, destination)
            copied[soname] = str(resolved)
            queue.append(resolved)

            owners = subprocess.run(
                ["dpkg-query", "-S", str(resolved)], text=True, capture_output=True
            )
            if owners.returncode == 0:
                for line in owners.stdout.splitlines():
                    pkg = line.split(": ", 1)[0].split(":", 1)[0]
                    copyright_file = Path("/usr/share/doc") / pkg / "copyright"
                    if copyright_file.is_file():
                        shutil.copy2(copyright_file, licenses / (pkg + "-copyright.txt"))

    # Relocatable lookup paths; modify only files inside the new package.
    elf_files = initial_elfs + sorted(lib.iterdir())
    for obj in elf_files:
        relative_lib = os.path.relpath(lib, obj.parent)
        rpath = "$ORIGIN" if relative_lib == "." else "$ORIGIN/" + relative_lib
        run(["patchelf", "--set-rpath", rpath, str(obj)])
        run(["strip", "--strip-unneeded", str(obj)])

    launcher = root / "launch.sh"
    launcher.write_text(
        '#!/bin/sh\nset -eu\n'
        'app_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)\n'
        'export LD_LIBRARY_PATH="$app_dir/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"\n'
        'export QT_PLUGIN_PATH="$app_dir/plugins"\n'
        'export QT_QPA_PLATFORM_PLUGIN_PATH="$app_dir/plugins/platforms"\n'
        'if [ -z "${QT_QPA_PLATFORM:-}" ] && [ -n "${DISPLAY:-}" ]; then\n'
        '  export QT_QPA_PLATFORM=xcb\n'
        'fi\n'
        'cd "$app_dir"\nexec "$app_dir/Vita3K" "$@"\n',
        encoding="utf-8",
    )
    launcher.chmod(0o755)
    (root / "qt.conf").write_text(
        "[Paths]\nPrefix=.\nPlugins=plugins\nLibraries=lib\nTranslations=translations\n",
        encoding="utf-8",
    )
    status = run(["git", "-C", str(args.source), "submodule", "status", "--recursive"]).stdout
    (root / "SOURCE.txt").write_text(
        "Vita3K Plus: https://github.com/nckstwrt/Vita3K-Plus\n"
        f"Commit: {args.source_sha}\n"
        "Qt SDK: 6.11.0 linux_gcc_arm64 (official Qt packages)\n"
        "Qt sources: https://download.qt.io/official_releases/qt/6.11/6.11.0/\n"
        "Build scripts: https://github.com/Icchi16/vita3k-plus-switchroot\n"
        "Build support: CLI early-exit guard, bounded LibAtrac9 API, generated metadata.\n"
        "Exact patches and metadata generator included in build-support/.\n\n"
        "Submodule revisions:\n" + status,
        encoding="utf-8",
    )
    (root / "README.txt").write_text(
        "Vita3K Plus - Ubuntu Noble 24.04 ARM64\n\n"
        "Extract on a Linux filesystem, then run ./launch.sh from your desktop session.\n"
        "If executable permissions were lost: chmod +x launch.sh Vita3K\n"
        "Qt and non-driver runtime libraries are included.\n"
        "Uses your existing Switchroot glibc and NVIDIA Tegra graphics drivers.\n"
        "Keep the NVIDIA driver packages supplied by Switchroot.\n"
        "No games, firmware, saves, or user configuration are included.\n"
        "Build verification covers ELF architecture, dependencies, --help and --version.\n"
        "Switch GPU rendering and gameplay still require testing on your Switch.\n",
        encoding="utf-8",
    )

    verification = {
        "source_sha": args.source_sha,
        "configuration": "Release",
        "architecture": "AArch64",
        "target": "Ubuntu Noble 24.04",
        "bundled_libraries": sorted(copied),
        "host_libraries": sorted(host_libraries),
        "smoke_checks": [],
        "switch_gameplay_tested": False,
    }
    # Test a relocated copy and an isolated user directory, using bundled Qt.
    with tempfile.TemporaryDirectory(prefix="vita3k-relocation-", dir=output) as tmp:
        tmp = Path(tmp)
        relocated = tmp / name
        shutil.copytree(root, relocated)
        test_env = os.environ.copy()
        for key in ("LD_LIBRARY_PATH", "QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH",
                    "DISPLAY", "WAYLAND_DISPLAY", "Qt6_ROOT", "QT_PREFIX"):
            test_env.pop(key, None)
        test_env.update({
            "HOME": str(tmp / "home"),
            "XDG_CONFIG_HOME": str(tmp / "config"),
            "XDG_DATA_HOME": str(tmp / "data"),
            "XDG_CACHE_HOME": str(tmp / "cache"),
            "QT_QPA_PLATFORM": "offscreen",
            "LD_LIBRARY_PATH": str(relocated / "lib"),
        })
        Path(test_env["HOME"]).mkdir()
        for obj in [relocated / "Vita3K"] + sorted((relocated / "plugins").rglob("*.so")):
            dependencies(obj, test_env)
        for flag in ("--help", "--version"):
            result = subprocess.run(
                [str(relocated / "launch.sh"), flag], env=test_env,
                cwd=relocated, text=True, capture_output=True, timeout=30,
            )
            verification["smoke_checks"].append({
                "argument": flag, "exit_code": result.returncode,
                "stdout": result.stdout, "stderr": result.stderr,
            })
            (output / "verification.json").write_text(
                json.dumps(verification, indent=2), encoding="utf-8"
            )
            if result.returncode != 0:
                raise RuntimeError(f"Relocated {flag} check failed: {result.stderr}")
    (root / "verification.json").write_text(
        json.dumps(verification, indent=2), encoding="utf-8"
    )
    checksum_lines = []
    for path in sorted(root.rglob("*")):
        if path.is_file():
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            checksum_lines.append(f"{digest}  {path.relative_to(root).as_posix()}")
    (root / "MANIFEST.sha256").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")
    archive = output / "Vita3K-Plus-Noble-ARM64.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(root, arcname=root.name)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix(archive.suffix + ".sha256").write_text(
        f"{digest}  {archive.name}\n", encoding="utf-8"
    )
    print(f"Created {archive} ({archive.stat().st_size / 1024 / 1024:.1f} MiB)")

def main():
    parser = argparse.ArgumentParser()
    for key in ("binary", "qt", "source", "output"):
        parser.add_argument("--" + key, required=True, type=Path)
    parser.add_argument("--source-sha", required=True)
    args = parser.parse_args()
    try:
        make_package(args)
    except Exception as error:
        args.output.mkdir(parents=True, exist_ok=True)
        path = args.output / "verification.json"
        prior = json.loads(path.read_text()) if path.exists() else {}
        prior["packaging_error"] = str(error)
        path.write_text(json.dumps(prior, indent=2), encoding="utf-8")
        print(f"Packaging failed: {error}", file=sys.stderr)
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
