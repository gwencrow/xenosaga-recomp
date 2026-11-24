#include "runtime/gs/gs_frontend.h"
#include "runtime/ps2_memory.h"

#include <cstdint>
#include <iostream>
#include <vector>

namespace
{
    constexpr uint32_t kPage = 32;
    constexpr uint32_t kWidth = 512;
    constexpr uint32_t kHeight = 448;
    constexpr uint32_t kBufferWidth = 8;
    constexpr uint32_t kSourceX = 3;
    constexpr uint32_t kSourceY = 5;

    uint64_t display(uint64_t dy, uint64_t height)
    {
        return 636u | (dy << 12) | (4ull << 23) |
               ((5ull * kWidth - 1) << 32) | ((height - 1) << 44);
    }

    uint64_t dispfb(uint64_t page)
    {
        return page | (uint64_t{kBufferWidth} << 9) |
               (uint64_t{kSourceX} << 32) | (uint64_t{kSourceY} << 43);
    }

    void writeRows(GS &gs, uint32_t page)
    {
        for (uint32_t y = kSourceY; y < kSourceY + kHeight; ++y)
            gs.WriteVram(GS_PSM_CT32, page * 32, kBufferWidth, kSourceX, y,
                         0x80000000u | (kSourceX << 16) | y);
    }

    bool check(GS &gs, GSRegisters &regs, const char *name, uint32_t expectedHeight, bool bob)
    {
        for (uint32_t parity = 0; parity < 2; ++parity)
        {
            regs.vsyncTick.store(2 + parity);
            gs.latchHostPresentationFrame();
            gs.sync();
            std::vector<uint8_t> pixels;
            uint32_t width = 0, height = 0;
            if (!gs.copyLatchedHostPresentationFrame(pixels, width, height) ||
                width != kWidth || height != expectedHeight)
            {
                std::cerr << name << ": unexpected frame size\n";
                return false;
            }
            for (uint32_t y = 0; y < height; ++y)
            {
                const uint32_t source = kSourceY + (bob ? (y & ~1u) + parity : y);
                const uint8_t *pixel = pixels.data() + y * width * 4;
                if ((uint32_t{pixel[0]} | (uint32_t{pixel[1]} << 8)) != source ||
                    pixel[2] != kSourceX || pixel[3] != 255)
                {
                    std::cerr << name << ": unexpected sample at row " << y
                              << " for parity " << parity << '\n';
                    return false;
                }
            }
        }
        return true;
    }
}

int main()
{
    GSRegisters regs{};
    std::vector<uint8_t> vram(4 * 1024 * 1024);
    GS gs;
    gs.init(vram.data(), static_cast<uint32_t>(vram.size()), &regs);
    regs.smode2 = 1; // Interlaced field mode.
    regs.pmode = 0x8027; // Both circuits, constant alpha, same source.
    regs.dispfb1 = regs.dispfb2 = dispfb(kPage);
    regs.display1 = display(49, kHeight);
    regs.display2 = display(50, kHeight);
    writeRows(gs, kPage);
    writeRows(gs, kPage + 128);

    if (!check(gs, regs, "default interlaced", kHeight, true))
        return 1;
    gs.setFullFramePresentation(true);
    gs.setAsync(true);
    if (!check(gs, regs, "same-buffer dual circuit", kHeight, false))
        return 1;

    regs.dispfb2 = dispfb(kPage + 128);
    if (!check(gs, regs, "different display buffers", kHeight, true))
        return 1;

    regs.pmode = 2;
    if (!check(gs, regs, "single display circuit", kHeight, false))
        return 1;

    regs.display2 = display(50, 224);
    if (!check(gs, regs, "short field buffer", 224, true))
        return 1;
    regs.smode2 = 3; // Interlaced frame mode.
    if (!check(gs, regs, "interlaced frame mode", 224, false))
        return 1;
    regs.smode2 = 0;
    return check(gs, regs, "progressive mode", 224, false) ? 0 : 1;
}
