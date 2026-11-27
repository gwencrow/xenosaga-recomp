#!/usr/bin/env bash
# Generate the synthetic GIF fixtures used by the Vulkan GS host tests (a03_gs_vk_runtime_tests) and
# verify them against SHA256SUMS. All fixture data is computed by the scripts in this directory.
#
# Usage: tests/vulkan-fixtures/make_fixtures.sh <output-directory>
#   creates <output-directory>/{orig,split,scaling-v2}; the directory must not exist yet.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd -P)
out=${1:?usage: make_fixtures.sh <output-directory>}
[[ ! -e $out ]] || { echo "exists: $out" >&2; exit 1; }
mkdir -p "$out"
python3 -I -B "$here/gen_orig.py" "$out/orig"
python3 -I -B "$here/gen_split.py" "$out/orig" "$out/split"
python3 -I -B "$here/scaling_fixture_v2.py" generate "$out/scaling-v2"
(cd "$out" && sha256sum --quiet -c "$here/SHA256SUMS")
echo "fixtures verified: $out"
