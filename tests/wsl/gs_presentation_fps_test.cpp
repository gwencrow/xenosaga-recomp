#include "runtime/gs/gs_frontend.h"
#include "runtime/ps2_memory.h"
#include <cstdio>
#include <cstdint>
#include <vector>

uint64_t ps2x_presentedFrameCount();

namespace
{
bool check(bool async)
{
    GSRegisters regs{};
    std::vector<uint8_t> vram(4u << 20);
    GS gs;
    gs.init(vram.data(), vram.size(), &regs);
    gs.setAsync(async);
    regs.display1 = (7ull << 32) | (7ull << 44);
    const uint64_t before = ps2x_presentedFrameCount();
    const auto present = [&](unsigned page) {
        regs.dispfb1 = (1ull << 9) | page;
        gs.latchHostPresentationFrame();
        gs.sync();
        return ps2x_presentedFrameCount() - before;
    };
    const auto blank = present(3);
    regs.pmode = 1;
    const auto first = present(3);
    const auto duplicate = present(3);
    const auto next = present(4);
    gs.setAsync(false);
    std::printf("async=%d invalid=%llu first=%llu duplicate=%llu flip=%llu\n", async,
                (unsigned long long)blank, (unsigned long long)first,
                (unsigned long long)duplicate, (unsigned long long)next);
    return blank == 0 && first == 1 && duplicate == 1 && next == 2;
}

}

int main()
{
    const bool syncPass = check(false);
    const bool asyncPass = check(true);
    return syncPass && asyncPass ? 0 : 1;
}
