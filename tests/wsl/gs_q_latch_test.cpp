#include "runtime/gs/gs_frontend.h"
#include "runtime/gs/gs_frontend.h"
#include <array>
#include <bit>
#include <cstdint>
#include <cstdio>
#include <initializer_list>
#include <memory>
#include <stdexcept>
#include <vector>

struct Sink : GSRasterBackend
{
    std::vector<uint32_t> qs;
    void Initialize(uint8_t *, uint32_t) override {}
    void Reset() override { qs.clear(); }
    void Submit(const GSPrimitiveBatch &batch) override
    {
        for (unsigned i = 0; i < batch.vertexCount; ++i)
            qs.push_back(std::bit_cast<uint32_t>(batch.vertices[i].q));
    }
    void LoadClut(const GSTex0Reg &, const GSTexClutReg &) override {}
    void BeginTransfer(const GSTransferCommand &) override {}
    void UploadImage(const uint8_t *, uint32_t) override {}
    void Flush() override {}
    void TextureFlush() override {}
    void Sync(GSSyncReason) override {}
    PresentationFrame Present(const GSPresentationRequest &) override { return {}; }
    bool ClearFramebuffer(const GSContext &, uint32_t) override { return false; }
    uint32_t ConsumeLocalToHostBytes(uint8_t *, uint32_t) override { return 0; }
    uint32_t ReadVram(uint32_t, uint32_t, uint32_t, uint32_t, uint32_t) const override { return 0; }
    void WriteVram(uint32_t, uint32_t, uint32_t, uint32_t, uint32_t, uint32_t) override {}
    void SnapshotVram(std::vector<uint8_t> &) const override {}
    GSTransferSnapshot GetTransferSnapshot() const override { return {}; }
};

using Word = std::array<uint64_t, 2>;
using Packet = std::vector<Word>;
constexpr uint32_t one = 0x3f800000, two = 0x40000000, half = 0x3f000000;
constexpr uint32_t white = 0x80808080;
constexpr Word rgba{0x8000000080ull, 0x8000000080ull};
constexpr Word kick{(8ull << 32) | 8, 1};
constexpr Word st(uint32_t q) { return {0x3e8000003e800000ull, q}; }

void tag(Packet &packet, unsigned format, std::initializer_list<unsigned> regs,
         std::initializer_list<Word> payload, bool eop = true)
{
    uint64_t descriptors = 0;
    unsigned shift = 0;
    for (unsigned reg : regs)
    {
        descriptors |= uint64_t(reg) << shift;
        shift += 4;
    }
    packet.push_back({1ull | (uint64_t(eop) << 15) | (uint64_t(format) << 58) |
                      (uint64_t(regs.size()) << 60), descriptors});
    packet.insert(packet.end(), payload);
}

int failures = 0;
void qTests()
{
    std::vector<uint8_t> vram(4u << 20);
    GS gs;
    gs.init(vram.data(), vram.size());
    auto sink = std::make_unique<Sink>();
    auto &seen = sink->qs;
    gs.setRasterBackend(std::move(sink));
    gs.writeRegister(0x00, 0);
    auto check = [&](const char *name, const Packet &p,
                     std::initializer_list<uint32_t> expected, bool native = false)
    {
        auto *data = reinterpret_cast<const uint8_t *>(p.data());
        if (native)
        {
            if (!gs.processNativePackedGIFPacket(data, p.size() * sizeof(Word)))
                throw std::runtime_error("native packet rejected");
        }
        else
            gs.processGIFPacket(data, p.size() * sizeof(Word));
        gs.sync();
        if (seen != std::vector<uint32_t>(expected))
            ++failures;
        std::printf("Q %-24s parser=%s actual=", name, native ? "native" : "generic");
        for (auto q : seen) std::printf("%08x ", q);
        std::printf("expected=");
        for (auto q : expected) std::printf("%08x ", q);
        std::puts("");
        seen.clear();
    };

    Packet packet;
    tag(packet, 0, {1,2,5,2,5,1,5}, {rgba,st(two),kick,st(half),kick,rgba,kick});
    check("st-without-refresh", packet, {one,one,half});
    packet.clear();
    tag(packet, 0, {2,1,5,2,1,5}, {st(two),rgba,kick,st(half),rgba,kick});
    check("refresh", packet, {two,half}, true);
    packet.clear();
    tag(packet, 0, {5,1,5}, {kick,rgba,kick});
    check("new-tag", packet, {half,one});
    packet.clear();
    tag(packet, 1, {1,2,5}, {{uint64_t(two) << 32 | white, st(0)[0]}, {0x100080008ull, 0}});
    check("reglist-odd", packet, {two});
    packet.clear();
    tag(packet, 0, {14,5,1,5}, {{uint64_t(half) << 32 | white, 1},kick,rgba,kick});
    check("direct-rgbaq", packet, {half,one});
    packet.clear();
    tag(packet, 0, {2,1,5}, {st(two),rgba,kick}, false);
    tag(packet, 0, {5,1,5}, {kick,rgba,kick});
    check("two-tags", packet, {two,two,one}, true);
    packet.clear();
    tag(packet, 0, {2,1,5,2,1,5,2,1,5,2,1,5},
        {st(0),rgba,kick,st(0x80000000),rgba,kick,st(1),rgba,kick,st(0x807fffff),rgba,kick});
    check("st-special-port-policy", packet, {one,one,1,0x807fffff});
    packet.clear();
    tag(packet, 1, {1,5,1,5}, {{white, 0x100080008ull},
        {uint64_t(0x00400000) << 32 | white, 0x100080008ull}});
    check("reglist-special-policy", packet, {one,0x00400000});
}

void texturedQ()
{
    // S = 5/16, width 8. For Q=1,2,0.5, floor(S*8/Q) is 2,1,5.
    // All three land at a texel center. T=0 and height=1 keep the row fixed.
    constexpr uint32_t palette[] = {
        0x80000011, 0x80003300, 0x80550000, 0x80006789,
        0x8098a001, 0x80e915ce, 0x80bf45a0, 0x80ffffff};
    Packet packet;
    tag(packet, 0, {14,14,14,14}, {{32ull << 32 | 1ull << 48,0x50},
        {0,0x51},{8ull | 1ull << 32,0x52},{0,0x53}}, false);
    packet.push_back({2ull | 2ull << 58, 0}); // IMAGE, two qwords.
    for (unsigned i=0; i<8; i+=4)
        packet.push_back({palette[i] | uint64_t(palette[i+1]) << 32,
                          palette[i+2] | uint64_t(palette[i+3]) << 32});
    tag(packet, 0, {14,14,14,14,14,14,14,14,14,14},
        {{22,0},{1ull << 16,0x4c},{1ull << 32,0x4e},{1ull << 17,0x47},
         {15ull << 16 | 7ull << 48,0x40},{0,0x18},{0,0x3f},
         {32ull | 1ull << 14 | 3ull << 26 | 1ull << 34 | 1ull << 35,0x06},
         {1,0x14},{5,0x08}}, false);
    auto xyz = [](unsigned x, unsigned y) -> Word {
        return {uint64_t(x*16) | uint64_t(y*16) << 32, 1};
    };
    auto coord = [](uint32_t q) -> Word { return {0x3ea00000u, q}; };
    tag(packet, 0, {1,2,5,5,1,5,5,2,1,5,5},
        {rgba,coord(two),xyz(0,0),xyz(2,2),
         rgba,xyz(2,0),xyz(4,2),
         coord(half),rgba,xyz(4,0),xyz(6,2)});
    std::vector<uint8_t> vram(4u << 20);
    GS gs;
    gs.init(vram.data(), vram.size());
    gs.processGIFPacket(reinterpret_cast<const uint8_t *>(packet.data()), packet.size() * sizeof(Word));
    gs.refreshDisplaySnapshot();
    const std::array<unsigned,3> expected{2,1,5};
    for (unsigned i=0; i<expected.size(); ++i)
    {
        const uint32_t actual = gs.ReadVram(0, 0, 1, i*2, 0);
        const uint32_t wanted = palette[expected[i]];
        std::printf("textured Q sprite %u actual=%08x expected=%08x\n",i,actual,wanted);
        if (actual != wanted) ++failures;
    }
}

int main()
{
    qTests();
    texturedQ();
    return failures != 0;
}
