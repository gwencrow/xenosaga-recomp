# Vulkan renderer (experimental)

The optional Vulkan renderer sends the game's raw GIF stream (PATH1, PATH2 and PATH3, after arbitration)
to [paraLLEl-GS](https://github.com/Arntzen-Software/parallel-gs), which emulates the GS on the GPU. It runs
on the existing GS worker thread. All Granite and Vulkan objects are created, used and destroyed there.
The OpenGL and CPU renderers are unchanged. Use them as references when you diagnose a Vulkan problem.

## Status

| Item | State |
|---|---|
| Validated system | Windows 11, Intel Core i9-13900K, NVIDIA GeForce RTX 4090, 64 GB RAM |
| Attended gameplay on that system | Native (X1), 2x (X4), 2x + 8 samples (X8), 2x + 16 samples (X16); combat, area transitions, Game Over and save reload; the Woglinde EXIT and EVS markers; an OpenGL control run; a validation-layer run with no validation messages; the driver-hidden and fault-injection initialization-failure controls; normal shutdown; the standalone device test suites |
| Performance (2x/X16, one attended run) | average 28 FPS, median 30 FPS; drops around the central Woglinde terminals. Gameplay observation, not a controlled benchmark |
| Other GPUs and drivers (AMD, Intel, older NVIDIA) | untested |
| Linux gameplay | not a target; the host test suites run on Linux with llvmpipe |
| Launcher build | does not include the renderer yet (build it with the WSL2 workflow) |

Known limitations: cinematic audio synchronization, frame-rate drops in demanding areas, and the general
emulation-accuracy issues listed in the README. The vertical shadow streaking seen with OpenGL was not
seen with Vulkan in the tested scenes.

## Settings

Add the keys to `settings.ini` (any section) or set the environment variable, which takes precedence.

| Setting | Environment | Values | Meaning |
|---|---|---|---|
| `renderer` | `PS2X_RENDERER` | `vulkan`, `gpu`, `cpu` | `vulkan` selects this renderer |
| `upscale` | `PS2X_UPSCALE` | `1`, `2` | `1` = native (X1); `2` = genuine 2x internal resolution (X4). `3`/`4` fall back to `2` with a message |
| `vulkan_aa` | `PS2X_VK_AA` | `0`, `8`, `16` | with `upscale = 2`: 8 or 16 samples per pixel (X8, X16) |
| `vulkan_fallback` | `PS2X_VK_FALLBACK` | `none` (default), `gpu`, `cpu` | on initialization failure: exit with a diagnostic, or continue with that renderer (announced in the console and window title) |
| `vulkan_validation` | `PS2X_VK_VALIDATION` | `true` / `false` | enable the Khronos validation layer (requires the Vulkan SDK layers) |
| `vulkan_progressive` | `PS2X_VK_PROGRESSIVE` | `true` (default) | progressive scanout of interlaced modes |
| `vulkan_gpu_timestamps` | `PS2X_VK_TIMESTAMPS` | `true` / `false` | GPU timing in the heartbeat statistics |
| `vulkan_idle_flush` | `PS2X_VK_IDLE_FLUSH` | `true` / `false` | diagnostic: flush on GS idle |

Recommended on the validated system: `renderer = vulkan`, `upscale = 2`, `vulkan_aa = 16`.

## Diagnostics

- The console log reports `[gs-vk] ACTIVE: …` with the device, driver and effective sample count. A failure
  is reported as `[gs-vk] FAILED: …`, together with the loader environment and whether the process is
  elevated (the loader ignores some `VK_*` variables in elevated processes).
- Shutdown is staged and logged (`[gs-vk] shutdown stage: …`). The renderer is torn down before Granite's
  `wait_idle`. `PS2X_GS_SHUTDOWN_REPORT_S=n` reports a slow shutdown after `n` seconds.
- The heartbeat (`src/xenosaga_debug.cpp`) prints GS queue and device statistics. It includes a report-only
  stall watchdog. With Vulkan the host copy of GS memory is stale, so `xs_vram.bin` is not written.
- GS capture: `PS2X_GS_CAPTURE_MB=n` keeps an `n` MB ring of the GS input. It is written as `.xgsr` on a
  renderer warning, a stall or close (`PS2X_GS_CAPTURE_DIR`, `PS2X_GS_CAPTURE_ON_WARNING`,
  `PS2X_GS_CAPTURE_MAX_DUMPS`). `a05_gs_replay` and `a06_gs_replay_timed` replay a capture offline. The
  record types are listed in `ps2xRuntime/include/runtime/gs/gs_capture.h`.
  **Captures contain game data. Keep them private.**
- `PS2X_VK_FAULT_INJECT=loader|instance|device|renderer` makes initialization fail on purpose at that
  stage. It is a test-only control for the failure policy.

## Tests

The runtime patch adds host suites under `ps2xTest/a03`–`a06` (built with `PS2X_BUILD_TEST=ON` and
`PS2X_ENABLE_PGS=ON`). They run on Linux with Mesa llvmpipe and, as cross-compiled executables, on Windows:

| Target | Covers |
|---|---|
| `a03_gif_ingress_tests` | raw and legacy GIF ingress paths |
| `a03_gs_vk_runtime_tests` | runtime integration of the device against a reference matrix; synthetic fixtures from [`tests/vulkan-fixtures`](../tests/vulkan-fixtures/README.md) (maintainer suite: the reference harness is not in the repository yet) |
| `a04_vk_display_tests` | CRT/display initialization, NTSC scanout, presentation modes |
| `a04_vk_shutdown_tests <scenario>` | 13 teardown scenarios, including `init-failure` (exit 0 = pass; must run non-elevated on Windows) |
| `a05_xs_render_tests` | DrawEnv, texture, CLUT and blending paths used by the game (`--validation`) |
| `a05_gs_capture_tests <dir>` | capture/replay integrity, warning triggers, fault injection, driver-hidden control |
| `a06_dma_chain_tests` | DMA source-chain traversal beyond 4096 tags, CALL/RET, TTE, cycle proof |

Report the existing failures of the broad `ps2x_tests` suite separately from new ones (see CONTRIBUTING).

## Licenses

The renderer uses these components. They are fetched by `tools/setup_parallel_gs.sh` at the listed
revisions and are not part of this repository:

| Component | Revision | License | Copyright | Use |
|---|---|---|---|---|
| [paraLLEl-GS](https://github.com/Arntzen-Software/parallel-gs) | `cc6184a` | LGPL-3.0-or-later | Arntzen Software AS | static library; modified by `patches/parallel-gs.patch` |
| [Granite](https://github.com/Themaister/Granite) | `16e7395` | MIT | Hans-Kristian Arntzen | static libraries (Vulkan backend and utilities) |
| [volk](https://github.com/zeux/volk) | `47cddf7` | MIT | Arseny Kapoulkine | static library; loads the driver's `vulkan-1.dll` at run time |
| [Vulkan-Headers](https://github.com/KhronosGroup/Vulkan-Headers) | `11d6898` | Apache-2.0 or MIT (per file) | The Khronos Group Inc. | headers only |

`patches/parallel-gs.patch` is a modification of paraLLEl-GS and is provided under the LGPL-3.0-or-later.
The Vulkan loader comes from the graphics driver. Anyone who distributes a binary must meet these licenses:
include the GPL-3.0 and LGPL-3.0 texts, the MIT and Apache-2.0 notices, and, for the statically linked
paraLLEl-GS, the material the LGPL requires for relinking. This project does not distribute binaries,
because every build contains the recompiled game.
