#include "runtime/gs/gs_cpu_backend.h"
#include "runtime/gs/gs_frontend.h"
#include "runtime/ps2_memory.h"

#include <array>
#include <chrono>
#include <condition_variable>
#include <cstdio>
#include <cstdint>
#include <memory>
#include <mutex>
#include <vector>
#include <utility>

namespace
{
constexpr uint64_t display = (63ull << 32) | (63ull << 44);
constexpr uint64_t dispfb(unsigned page) { return (1ull << 9) | page; }

struct Sample
{
    unsigned page, contextPage, red;
    bool operator==(const Sample &) const = default;
};

struct ControlledCpu final : GSRasterBackend
{
    GSCpuBackend cpu;
    std::mutex mutex;
    std::condition_variable gate;
    bool entered = false;
    bool released = false;
    std::vector<Sample> samples;

    void Initialize(uint8_t *vram, uint32_t bytes) override { cpu.Initialize(vram, bytes); }
    void Submit(const GSPrimitiveBatch &batch) override { cpu.Submit(batch); }
    void Flush() override { cpu.Flush(); }
    void Sync(GSSyncReason reason) override { cpu.Sync(reason); }

    void Reset() override { cpu.Reset(); }
    void LoadClut(const GSTex0Reg &, const GSTexClutReg &) override {}
    void BeginTransfer(const GSTransferCommand &) override {}
    void UploadImage(const uint8_t *, uint32_t) override {}
    void TextureFlush() override {}
    bool ClearFramebuffer(const GSContext &, uint32_t) override { return false; }
    uint32_t ConsumeLocalToHostBytes(uint8_t *, uint32_t) override { return 0; }
    uint32_t ReadVram(uint32_t, uint32_t, uint32_t, uint32_t, uint32_t) const override { return 0; }
    void WriteVram(uint32_t, uint32_t, uint32_t, uint32_t, uint32_t, uint32_t) override {}
    void SnapshotVram(std::vector<uint8_t> &) const override {}
    GSTransferSnapshot GetTransferSnapshot() const override { return {}; }

    PresentationFrame Present(const GSPresentationRequest &request) override
    {
        {
            std::unique_lock lock(mutex);
            entered = true;
            gate.notify_one();
            gate.wait(lock, [&] { return released; });
        }
        PresentationFrame frame = cpu.Present(request);
        samples.push_back({frame.sourceFbp, request.contextFrames[0].fbp,
                           frame ? frame.pixels.front() : 256u});
        return frame;
    }

    bool waitForWorker()
    {
        std::unique_lock lock(mutex);
        return gate.wait_for(lock, std::chrono::seconds(5), [&] { return entered; });
    }

    void releaseWorker()
    {
        {
            std::lock_guard lock(mutex);
            released = true;
        }
        gate.notify_one();
    }
};

void submitPoint(GS &gs, unsigned page, unsigned red)
{
    // PACKED A+D. FRAME, ZBUF with writes masked, scissor, TEST with depth ALWAYS, point, color, XYZ2.
    constexpr uint64_t tag = 7 | (1ull << 15) | (1ull << 60);
    const std::array<std::array<uint64_t, 2>, 8> packet{{
        {tag, 0xe},
        {page | (1ull << 16), 0x4c},
        {1ull << 32, 0x4e},
        {(7ull << 16) | (7ull << 48), 0x40},
        {1ull << 17, 0x47},
        {0, 0x00},
        {red | 0x80000000ull | (0x3f800000ull << 32), 0x01},
        {0, 0x05},
    }};
    gs.processGIFPacket(reinterpret_cast<const uint8_t *>(packet.data()), sizeof(packet));
}

bool check(const char *scenario, const std::vector<std::pair<unsigned, unsigned>> &presents,
           const std::vector<Sample> &expected, bool coalesce = false, bool varyDisplay1 = false)
{
    std::vector<uint8_t> vram(4u << 20);
    GSRegisters regs{};
    GS gs;
    gs.init(vram.data(), vram.size(), &regs);
    auto backend = std::make_unique<ControlledCpu>();
    auto &cpu = *backend;
    gs.setRasterBackend(std::move(backend));
    regs.pmode = 2; // Circuit 2 is the only active circuit.
    regs.display2 = display;
    regs.dispfb1 = dispfb(24); // Deliberately fixed.
    regs.dispfb2 = dispfb(1);
    gs.setAsync(true);
    submitPoint(gs, 1, 11);
    gs.latchHostPresentationFrame();
    const bool blocked = cpu.waitForWorker();
    if (blocked)
    {
        for (auto [page, red] : presents)
        {
            submitPoint(gs, page, red);
            // Make capacity replacements eligible in the original version.
            if (varyDisplay1)
                regs.dispfb1 = dispfb(page);
            regs.dispfb2 = dispfb(page);
            regs.vsyncTick.fetch_add(1);
            gs.latchHostPresentationFrame();
        }
        if (coalesce)
        {
            // A second host sample at the same command boundary.
            regs.dispfb2 = dispfb(1);
            regs.vsyncTick.fetch_add(1);
            gs.latchHostPresentationFrame();
        }
        // Later GIF work must never enter the last selected frame.
        submitPoint(gs, expected.back().page, 99);
    }
    cpu.releaseWorker();
    gs.sync();
    std::vector<uint8_t> pixels;
    uint32_t w = 0, h = 0, source = 0;
    const bool copied = gs.copyLatchedHostPresentationFrame(pixels, w, h, nullptr, &source);
    gs.setAsync(false);
    std::printf("%s (source page, executed FRAME page, red)\n", scenario);
    for (const auto &s : cpu.samples)
        std::printf("  observed (%u, %u, %u)\n", s.page, s.contextPage, s.red);
    for (const auto &s : expected)
        std::printf("  expected (%u, %u, %u)\n", s.page, s.contextPage, s.red);
    std::printf("  host copy valid=%d size=%ux%u page=%u red=%u\n", copied, w, h, source,
                pixels.empty() ? 256u : pixels.front());
    return blocked && cpu.samples == expected && copied && w == 64 && h == 64 &&
           source == expected.back().page && !pixels.empty() && pixels.front() == expected.back().red;
}
}

int main()
{
    bool sameDisplay1 = check("circuit-2", {{2,22},{3,33},{3,34}},
                              {{1,1,11},{2,2,22},{3,3,33},{3,3,34}});
    bool capacity = check("capacity", {{2,22},{3,33},{4,44},{5,55},{6,66},{7,77}},
                          {{1,1,11},{2,2,22},{3,3,33},{4,4,44},{7,7,77}}, false, true);
    bool sameBoundary = check("same-boundary", {{2,22}}, {{1,1,11},{1,2,11}}, true);
    return sameDisplay1 && capacity && sameBoundary ? 0 : 1;
}
