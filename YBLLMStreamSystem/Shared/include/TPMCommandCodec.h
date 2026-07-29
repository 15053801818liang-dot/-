#pragma once

#include <cstddef>
#include <cstdint>
#include <vector>

namespace PromptKit::TPM2 {

using Bytes = std::vector<std::uint8_t>;

struct EccPoint {
    Bytes x;
    Bytes y;
};

enum class SignatureScheme : std::uint16_t {
    Ecdsa = 0x0018,
    Ecdaa = 0x001A,
};

// TPM algorithm identifiers from the TPM 2.0 Library Specification.
inline constexpr std::uint16_t kAlgNull = 0x0010;
inline constexpr std::uint16_t kAlgSha256 = 0x000B;

struct CommitParameters {
    std::uint32_t signing_key_handle{};
    Bytes authorization;
    EccPoint p1;
    Bytes s2;
    Bytes y2;
};

struct SignParameters {
    std::uint32_t key_handle{};
    Bytes digest;
    SignatureScheme scheme{SignatureScheme::Ecdsa};
    std::uint16_t hash_algorithm{kAlgSha256};
    // Required for ECDAA. Ignored for ECDSA.
    std::uint16_t commit_counter{};
    Bytes authorization;
};

struct TpmResponse {
    std::uint16_t tag{};
    std::uint32_t response_code{};
    Bytes parameters;
};

Bytes BuildCommitCommand(const CommitParameters& parameters);
Bytes BuildSignCommand(const SignParameters& parameters);
TpmResponse ParseResponse(const Bytes& response);

// Commands use a TPM_RS_PW authorization session. Extracts the two TPM2B
// signature components from a successful ECDSA/ECDAA
// TPMT_SIGNATURE response. Returns r || s in a fixed-width, 64-byte format.
Bytes ParseEccSignature(const TpmResponse& response);

} // namespace PromptKit::TPM2
