// Copyright © 2026 SnapKitty Collective LLC. All rights reserved.
// Licensed under Business Source License 2.0 (BSL-2.0).
// Change Date: December 31, 2027 — after which, licensed under AGPL-3.0-only.
// See LICENSE for complete terms.

#pragma once
// PIRTM Linker — multi-pass linking with identity commitment and spectral checks

#include "types.h"
#include <vector>
#include <string>

namespace pmc {

struct LinkerConfig {
    size_t max_identity_duplicates;
    double spectral_coupling_bound;
};

struct LinkedArtifact {
    std::string name;
    std::vector<uint8_t> bytecode;
    std::vector<uint8_t> identity_hash;
    bool spectral_ok;
};

class Linker {
public:
    explicit Linker(const LinkerConfig& cfg);

    // Multi-pass linking
    std::vector<LinkedArtifact> link(
        const std::vector<std::vector<uint8_t>>& artifacts);

private:
    LinkerConfig config_;

    // Pass 1: Name resolution (aliases to bytecode)
    bool pass_name_resolution(std::vector<LinkedArtifact>& arts);

    // Pass 2: Identity commitment crosscheck (no duplicates)
    bool pass_identity_check(std::vector<LinkedArtifact>& arts);

    // Pass 3: Spectral small-gain test on global coupling matrix
    bool pass_spectral_test(std::vector<LinkedArtifact>& arts);
};

} // namespace pmc
