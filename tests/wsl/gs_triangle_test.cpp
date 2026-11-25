#include "runtime/gs/gs_frontend.h"

#include <algorithm>
#include <array>
#include <cstdint>
#include <cstdio>
#include <initializer_list>
#include <string>
#include <vector>

namespace
{
using Word = std::array<uint64_t, 2>;
using Packet = std::vector<Word>;
constexpr uint32_t one = 0x3f800000;
constexpr uint32_t white = 0x80808080;

void tag(Packet &packet, std::initializer_list<unsigned> regs,
         std::initializer_list<Word> payload)
{
    uint64_t descriptors = 0;
    unsigned shift = 0;
    for (unsigned reg : regs)
    {
        descriptors |= uint64_t(reg) << shift;
        shift += 4;
    }
    packet.push_back({1ull | (1ull << 15) |
                      (uint64_t(regs.size()) << 60), descriptors});
    packet.insert(packet.end(), payload);
}


int failures = 0;
using Point = std::array<int,2>;
void triangleTests()
{
    std::vector<uint8_t> vram(4u << 20);
    GS gs;
    gs.init(vram.data(), vram.size());
    auto draw = [&](const char *name, std::array<Point,3> points, Point offset,
                    const std::vector<std::string> &expected, unsigned scissorX = 5)
    {
        std::fill(vram.begin(), vram.end(), 0);
        Packet packet;
        auto xyz = [&](Point p) -> Word
        {
            return {uint64_t(p[0] + offset[0]) | (uint64_t(p[1] + offset[1]) << 16) | (1ull << 32), 5};
        };
        tag(packet, {14,14,14,14,14,14,14,14,14,14},
            {{3,0},{uint64_t(1) << 16,0x4c},{1ull << 32,0x4e},{1ull << 17,0x47},
             {uint64_t(scissorX) << 16 | uint64_t(expected.size() - 1) << 48,0x40},
             {uint64_t(offset[0]) | uint64_t(offset[1]) << 32,0x18},
             {white | (uint64_t(one) << 32),1},xyz(points[0]),xyz(points[1]),xyz(points[2])});
        gs.processGIFPacket(reinterpret_cast<const uint8_t *>(packet.data()), packet.size() * sizeof(Word));
        gs.refreshDisplaySnapshot();
        std::printf("Triangle %s actual / expected\n", name);
        for (unsigned y = 0; y < expected.size(); ++y)
        {
            std::string row;
            for (unsigned x = 0; x < expected[y].size(); ++x)
                row += gs.ReadVram(0, 0, 1, x, y) == white ? '#' : '.';
            if (row != expected[y]) ++failures;
            std::printf("  %s / %s\n", row.c_str(), expected[y].c_str());
        }
    };
    // Sample x,y each in 0..5. The first mask implements x+y<4.
    // The other includes the diagonal and excludes the outer bottom/right.
    const std::vector<std::string> upper{"####..","###...","##....","#.....","......","......"};
    const std::vector<std::string> lower{"......","...#..","..##..",".###..","......","......"};
    draw("upper-left", {{{0,0},{64,0},{0,64}}}, {32,48}, upper);
    draw("lower-right", {{{64,64},{0,64},{64,0}}}, {32,48}, lower);
    draw("reverse-winding", {{{0,64},{64,0},{0,0}}}, {37,55}, upper);
    draw("one-sixteenth-in", {{{1,0},{65,0},{1,64}}}, {32,48},
         {".####.",".###..",".##...",".#....","......","......"});
    draw("half-pixel", {{{8,0},{72,0},{8,64}}}, {32,48},
         {".####.",".###..",".##...",".#....","......","......"});
    draw("negative-and-clipped", {{{-16,0},{48,0},{-16,64}}}, {37,55},
         {"##....","##....","#.....","......","......","......"}, 1);
    draw("one-subpixel-area", {{{0,0},{1,0},{0,1}}}, {32,48},
         {"#.....","......","......","......","......","......"});
    draw("degenerate", {{{0,0},{32,32},{64,64}}}, {32,48},
         {"......","......","......","......","......","......"});

    // With eight workers, rows cross all eight raster bands in one draw.
    std::vector<std::string> allBands;
    for (unsigned y = 0; y < 64; ++y)
        allBands.push_back(std::string(64 - y, '#') + std::string(y, '.'));
    draw("all-worker-bands", {{{0,0},{1024,0},{0,1024}}}, {37,55}, allBands, 63);
}
}

int main()
{
    triangleTests();
    return failures != 0;
}
