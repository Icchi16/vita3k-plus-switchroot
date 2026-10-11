#!/usr/bin/env bash
set -euo pipefail
test "$(uname -m)" = aarch64
: "${QT_PREFIX:?Missing Qt SDK path}"
python3 scripts/prepare-source.py
mkdir -p build
cmake -S source -B build -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_C_COMPILER=clang \
  -DCMAKE_CXX_COMPILER=clang++ \
  -DCMAKE_C_FLAGS=-march=armv8-a \
  -DCMAKE_CXX_FLAGS=-march=armv8-a \
  -DQt6_ROOT="$QT_PREFIX" \
  -DCMAKE_PREFIX_PATH="$QT_PREFIX" \
  -DUSE_DISCORD_RICH_PRESENCE=OFF \
  -DBUILD_APPIMAGE=OFF \
  -DVITA3K_FORCE_SYSTEM_BOOST=ON \
  -DUSE_LTO=NEVER 2>&1 | tee build/configure.log
cmake --build build --target vita3k --parallel "${BUILD_JOBS:-2}" \
  2>&1 | tee build/compile.log
test -x build/bin/Vita3K
file build/bin/Vita3K
readelf -h build/bin/Vita3K | grep -q 'Machine:.*AArch64'
