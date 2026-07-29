// Copyright © 2026 SnapKitty Collective LLC. All rights reserved.
// Licensed under Business Source License 2.0 (BSL-2.0).
// Change Date: December 31, 2027 — after which, licensed under AGPL-3.0-only.
// See LICENSE for complete terms.

#pragma once
// SHA-256 chained append-only audit log (WORM)

#include "types.h"
#include "sha256.h"
#include <vector>
#include <fstream>

namespace pmc {

class AuditChain {
public:
    AuditChain();

    // Append event to chain — computes chained hash
    AuditEvent append(const std::string& label,
                      const uint8_t payload[32],
                      uint64_t timestamp_ns);

    // Verify entire chain from genesis
    bool verify() const;

    // Get genesis hash (all zeros)
    static std::array<uint8_t, 32> genesis_hash();

    // Serialize chain to JSONL
    bool write_jsonl(const std::string& path) const;

    // Load chain from JSONL
    bool load_jsonl(const std::string& path);

    const std::vector<AuditEvent>& events() const { return events_; }
    size_t size() const { return events_.size(); }

private:
    std::vector<AuditEvent> events_;
    std::array<uint8_t, 32> last_chain_hash_;

    // Compute event_hash = SHA256(canonical_payload)
    static std::array<uint8_t, 32> compute_event_hash(
        uint64_t index, const std::string& label,
        const std::array<uint8_t, 32>& prev_hash,
        const std::array<uint8_t, 32>& payload_hash,
        uint64_t timestamp_ns);

    // Compute chain_hash = SHA256(prev_chain_hash || event_hash)
    static std::array<uint8_t, 32> compute_chain_hash(
        const std::array<uint8_t, 32>& prev_chain,
        const std::array<uint8_t, 32>& event_hash);
};

} // namespace pmc
