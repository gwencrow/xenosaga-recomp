# Vulkan GS test fixtures

Synthetic GIF fixtures for `a03_gs_vk_runtime_tests`, the runtime-integration suite of the optional Vulkan
renderer. The scripts here compute every byte. No fixture is captured from the game or derived from game
data, and no generated data is committed. Run the generator to create the fixtures:

```sh
tests/vulkan-fixtures/make_fixtures.sh "$XS_ROOT/runs/vk-fixtures"
```

The script creates three directories and checks them against `SHA256SUMS`:

| Directory | Generator | Content |
|---|---|---|
| `orig/` | `gen_orig.py` | a 16x16 PSMCT32 gradient uploaded through IMAGE, drawn as a textured sprite into a second page, that page reused as a texture (alias sample), FINISH, a local->host readback and a 16x16 scanout. `expected-*.vram` and `expected-fifo.rgba` are the analytic model of the result |
| `split/` | `gen_split.py` | `orig/` with the IMAGE transfer cut in the middle of its payload and sent as two packets |
| `scaling-v2/` | `scaling_fixture_v2.py generate` | a 64x64 scene of 3D triangles, sub-pixel quads, an alpha-blended triangle, a minified textured quad, three UI-demotion probes and a feedback copy, used to verify genuine internal-resolution scaling. `scaling_fixture_v2.py compare` is its analytic comparator |

Each fixture has a `commands.txt` script (`gif <path> <file>`, `vram <name>`, `fifo <qwords> <name>`,
`scanout <phase> <PMODE> <SMODE1> <SMODE2> <DISPFB1> <DISPLAY1> <BGCOLOR> <name>`) and the GIF packets it
names.

## Running the suite

```sh
a03_gs_vk_runtime_tests FIXTURES REFERENCE_MATRIX OUT_DIR [--validation] [--modes native,2x,x8,x16]
```

`FIXTURES` is the output directory of `make_fixtures.sh`. `REFERENCE_MATRIX` holds the VRAM, FIFO and
scanout results of the same fixtures from a standalone paraLLEl-GS harness on the same Vulkan device
(`orig-<mode>/`, `split-<mode>/`, `v2-<mode>/`). The suite checks that the runtime integration produces
exactly those bytes. **The reference harness is not part of this repository yet**, so for now the suite
is a maintainer tool. The other Vulkan suites (`a04_*`, `a05_*`, `a06_*`) need no external data.

## Provenance

The generators were written for this port's paraLLEl-GS evaluation. They are covered by the repository
license (GPL-3.0). `SHA256SUMS` lists the exact fixtures the runtime suite was validated with on Linux
(Mesa llvmpipe). The scripts reproduce all 53 files byte for byte.
