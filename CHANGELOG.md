# Changelog

Notable changes to Xenosaga Episode I: Recompiled are recorded here. This project is still in development and does not yet have a stable release.

## Unreleased

### Runtime

- Fixed silent truncation of DMA source chains exceeding 4,096 tags, which could cause persistent texture and UI corruption or gameplay stalls. DMA traversal now continues to the terminating tag, with cycle detection and bounded safety guards.
- Validated the isolated DMA correction through 34 regression checks, sanitizer testing and native Windows OpenGL gameplay. The previously observed Woglinde graphical corruption was not reproduced, and 22 long DMA chains completed without reported truncation.

- Corrected SIF RPC callback stack handling to prevent synthetic stack writes from overwriting guest scene resources. RPC callbacks now use the caller's guest stack, addressing corruption responsible for missing EXIT and EVS markers in Woglinde.
- Added regression coverage for RPC guest stack preservation.

## 2026-11-26

### Development validation

- Successfully compiled and tested a fresh Windows runtime incorporating the merged November 25 corrections.
- Confirmed functional OpenGL gameplay and normal shutdown in attended baseline testing.
- Reproduced residual character-shadow streaking in the OpenGL renderer at native and 3x internal resolution.
- Observed native-resolution game FPS samples ranging from 16.4 to 28.8 on an Intel Core i9-13900K and NVIDIA RTX 4090.

### Experimental research

- Extended standalone paraLLEl-GS Vulkan validation on Linux and native Windows using NVIDIA hardware.
- Demonstrated genuine 2x per-axis internal GS rasterization and 2x output with additional antialiasing in controlled test workloads.
- Identified and tested a correction for resource allocation when requested sample counts exceed device capabilities.
- Identified potential performance improvements through persistent GS state and reduced unnecessary synchronization and readback.
- Continued investigation of native VU1 dispatch, interpreter fallback, CPU-side execution overhead and VIF1 synchronization.

Vulkan gameplay integration remains experimental and is not yet available in the public runtime. Outstanding cross-device rendering differences require further validation. Standalone renderer measurements do not establish whole-game performance improvements.

Related issues: [#6](https://github.com/gwencrow/xenosaga-recomp/issues/6), [#7](https://github.com/gwencrow/xenosaga-recomp/issues/7), [#11](https://github.com/gwencrow/xenosaga-recomp/issues/11), [#23](https://github.com/gwencrow/xenosaga-recomp/issues/23).

## 2026-11-25

### Runtime

- Corrected PACKED GIF Q latching, preserving the distinction between the GIF unpacker's internal Q value and the GS vertex latch. ([#29](https://github.com/gwencrow/xenosaga-recomp/pull/29))
- Corrected asynchronous GS presentation ordering. Menu flashing was eliminated in the tested configurations. ([#30](https://github.com/gwencrow/xenosaga-recomp/pull/30))
- Corrected integer triangle rasterization coverage in the CPU renderer, preserving fractional vertex coordinates and consistent edge ownership. ([#31](https://github.com/gwencrow/xenosaga-recomp/pull/31))
- Corrected GS presentation FPS counting in synchronous and asynchronous modes. This is an instrumentation correction rather than a rendering performance optimization. ([#32](https://github.com/gwencrow/xenosaga-recomp/pull/32))

### Build and testing

- Added generated function registrar validation to assembly, build, installation and staging workflows. ([#28](https://github.com/gwencrow/xenosaga-recomp/pull/28))
- Expanded regression coverage for GIF Q latching, triangle rasterization, presentation ordering and FPS counting.
- The integrated host regression suite passed 50 of 57 tests, with seven previously identified GS failures remaining unchanged.
- All 12 port-specific host checks and seven registrar regression tests passed.

### Known limitations

- Existing GS texture visibility, CLUT caching and memory alias regression failures remain unresolved.
- CPU triangle coverage improvements do not establish complete hardware rasterization equivalence.
- Broader gameplay validation remains necessary.

## 2026-11-24

### Runtime

- Fixed severe vertical shaking on the title screen at 1x internal resolution by presenting every row of the game's full-height framebuffer. The tested in-engine cutscenes also presented stably at 1x. ([#13](https://github.com/gwencrow/xenosaga-recomp/issues/13))
- Added strict validation of native VU1 blocks against the interpreter.
- Added ABI compatibility checks to prevent linking incompatible native block objects.
- Restricted experimental whole-program VU1 execution to offline replay.
- Validated native block execution across 3,600 captured calls on both Linux and Windows, with matching architectural state, GIF output and cycle counts.

### Build and testing

- Added a Debian WSL2 build workflow for Windows x64 using MinGW-w64 and FFmpeg.
- Added build preflight checks, repeatable executable relinking, DLL dependency verification and local staging tools.
- Added host regression tests and automated VU1 replay and gameplay comparison tools.
- Updated the launcher to skip automatic tuning when the training recording is unavailable. Manual optimization remains available after gameplay.
- Completed a Windows gameplay smoke test of the integration contribution.

### Performance

Controlled gameplay comparisons on the validated development baseline showed the following improvements with locally generated native VU1 blocks:

| Scene | Interpreter | Native blocks | Speedup |
|---|---:|---:|---:|
| Exploration (1x) | 85.1 s | 53.3 s | 1.60x |
| Exploration (3x) | 85.3 s | 52.5 s | 1.62x |
| Later gameplay (1x) | 61.9 s | 40.3 s | 1.54x |
| Later gameplay (3x) | 58.8 s | 46.3 s | 1.27x |

Test system: Intel Core i9-13900K, NVIDIA RTX 4090, 64 GB RAM, Windows 11, OpenGL.

These results represent one recorded route with one paired trial per resolution, not a full-game benchmark or a guaranteed improvement on every system.

### Documentation

- Updated the README, project banner and gameplay screenshots.
- Added the [WSL2 build guide](docs/BUILD_WSL.md) and [VU1 performance documentation](docs/VU1_PERFORMANCE.md).
- Clarified installation, manual optimization and known compatibility limitations.

### Known limitations

- Mild title-screen shaking at 3x was visible in both the original and corrected presentation modes.
- Mild flickering and bottom-edge artifacts in pre-rendered cutscenes remain unresolved. Bottom-edge artifacts were observed with both original and corrected native-resolution presentation.
- Demanding scenes remain below the 30 FPS target.
- In-engine cutscenes can exhibit significant audio desynchronization.
- Seven existing GS regression tests remain unresolved.
- Full Windows launcher installation and full-game compatibility have not been validated.

Related pull requests: [#1](https://github.com/gwencrow/xenosaga-recomp/pull/1), [#2](https://github.com/gwencrow/xenosaga-recomp/pull/2), [#3](https://github.com/gwencrow/xenosaga-recomp/pull/3).

## Earlier development

The original port was developed by [BeyondNeteros](https://github.com/BeyondNeteros/xenosaga-recomp-FREE-TO-USE). Earlier development history is preserved in Git. This changelog begins with the continued development of the fork.
