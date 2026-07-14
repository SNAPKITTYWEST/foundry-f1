#pragma once
// SHA-256 — NASM x86-64 fast path (PMC_SHA256_NASM=1) with C++ fallback

#include <cstdint>
#include <cstddef>
#include <array>

// NASM entry: void sha256_hash(const uint8_t* data, size_t len, uint8_t out[32])
#ifdef PMC_SHA256_NASM
extern "C" void sha256_hash(const uint8_t* data, size_t len, uint8_t out[32]);
#endif

namespace pmc {

class SHA256 {
public:
    using Digest = std::array<uint8_t, 32>;

    SHA256();
    void update(const uint8_t* data, size_t len);
    Digest finalize();

    // One-shot convenience
    static Digest hash(const uint8_t* data, size_t len);

private:
    uint32_t h_[8];
    uint64_t total_len_;
    uint8_t  buffer_[64];
    size_t   buffer_len_;

    void process_block(const uint8_t block[64]);
};

} // namespace pmc
