#!/usr/bin/env bash
# Prepare the paraLLEl-GS source used by the optional Vulkan GS device (renderer = vulkan).
#
# Usage: tools/setup_parallel_gs.sh <directory>
#
# Clones paraLLEl-GS at the pinned revision with the submodules a standalone build needs (Granite,
# volk, Vulkan-Headers; same selection as upstream checkout_submodules.sh), verifies the pins and
# applies patches/parallel-gs.patch once. An existing directory is verified and patched in place;
# a directory without Git metadata (an offline copy) is patched but its pins cannot be verified.
# Keep the checkout outside this repository and pass it to the build as PGS_SOURCE.
set -euo pipefail
port=$(cd "$(dirname "$0")/.." && pwd -P)
dir=${1:?usage: setup_parallel_gs.sh <directory>}
url=https://github.com/Arntzen-Software/parallel-gs.git
pin=cc6184af7e0c03da603045ca371ffa5dae9b0655
granite_pin=16e7395f6a4858c1783dbf6f521f90b9d5f82ac5
volk_pin=47cddf7ed97b94118a08aacb548a411188e016cc
headers_pin=11d6898377797e07dbd543aaaa367e4465074597
patch_file=$port/patches/parallel-gs.patch

if [[ ! -e $dir ]]; then
    git clone "$url" "$dir"
    git -C "$dir" checkout --detach "$pin"
    git -C "$dir" submodule update --init Granite
    git -C "$dir/Granite" submodule update --init third_party/volk third_party/khronos/vulkan-headers
fi
if [[ -e $dir/.git ]]; then
    check() {
        local got
        got=$(git -C "$1" rev-parse HEAD)
        [[ $got == "$2" ]] || { echo "$1 is at $got, expected $2" >&2; exit 1; }
    }
    check "$dir" "$pin"
    check "$dir/Granite" "$granite_pin"
    check "$dir/Granite/third_party/volk" "$volk_pin"
    check "$dir/Granite/third_party/khronos/vulkan-headers" "$headers_pin"
    echo "paraLLEl-GS $pin, Granite $granite_pin, volk $volk_pin, Vulkan-Headers $headers_pin"
else
    echo "warning: $dir has no Git metadata; revisions not verified" >&2
fi
if patch -d "$dir" -p1 -R --dry-run -s -f < "$patch_file" >/dev/null; then
    echo "patches/parallel-gs.patch already applied"
else
    patch -d "$dir" -p1 --dry-run -s -f < "$patch_file" >/dev/null
    patch -d "$dir" -p1 -s -f < "$patch_file"
    echo "applied patches/parallel-gs.patch"
fi
echo "PGS_SOURCE=$(cd "$dir" && pwd -P)"
