#include "TPMCommandCodec.h"

#include <algorithm>
#include <limits>
#include <stdexcept>

namespace PromptKit::TPM2 {
namespace {

constexpr std::uint16_t kTagSessions = 0x8002;
constexpr std::uint32_t kCommandCommit = 0x0000018B;
constexpr std::uint32_t kCommandSign = 0x0000015D;

void PutU16(Bytes& out, std::uint16_t value) {
    out.push_back(static_cast<std::uint8_t>(value >> 8));
    out.push_back(static_cast<std::uint8_t>(value));
}

void PutU32(Bytes& out, std::uint32_t value) {
    out.push_back(static_cast<std::uint8_t>(value >> 24));
    out.push_back(static_cast<std::uint8_t>(value >> 16));
    out.push_back(static_cast<std::uint8_t>(value >> 8));
    out.push_back(static_cast<std::uint8_t>(value));
}

std::uint16_t GetU16(const Bytes& in, std::size_t& offset) {
    if (offset + 2 > in.size()) throw std::invalid_argument("truncated TPM UINT16");
    const auto value = static_cast<std::uint16_t>((in[offset] << 8) | in[offset + 1]);
    offset += 2;
    return value;
}

std::uint32_t GetU32(const Bytes& in, std::size_t& offset) {
    if (offset + 4 > in.size()) throw std::invalid_argument("truncated TPM UINT32");
    const auto value = (static_cast<std::uint32_t>(in[offset]) << 24) |
                       (static_cast<std::uint32_t>(in[offset + 1]) << 16) |
                       (static_cast<std::uint32_t>(in[offset + 2]) << 8) |
                       static_cast<std::uint32_t>(in[offset + 3]);
    offset += 4;
    return value;
}

void PutTpm2B(Bytes& out, const Bytes& value) {
    if (value.size() > std::numeric_limits<std::uint16_t>::max()) {
        throw std::invalid_argument("TPM2B value exceeds UINT16 size");
    }
    PutU16(out, static_cast<std::uint16_t>(value.size()));
    out.insert(out.end(), value.begin(), value.end());
}

void PutPoint(Bytes& out, const EccPoint& point) {
    Bytes encoded;
    PutTpm2B(encoded, point.x);
    PutTpm2B(encoded, point.y);
    PutTpm2B(out, encoded);
}

Bytes Finish(std::uint32_t command_code, std::uint32_t handle, const Bytes& authorization, Bytes parameters) {
    Bytes body;
    PutU32(body, handle);
    Bytes auth_area;
    PutU32(auth_area, 0x40000009); // TPM_RS_PW
    PutU16(auth_area, 0);          // empty nonce
    auth_area.push_back(0);        // TPMA_SESSION
    PutTpm2B(auth_area, authorization);
    PutU32(body, static_cast<std::uint32_t>(auth_area.size()));
    body.insert(body.end(), auth_area.begin(), auth_area.end());
    body.insert(body.end(), parameters.begin(), parameters.end());
    const auto size = 10ULL + body.size();
    if (size > std::numeric_limits<std::uint32_t>::max()) {
        throw std::invalid_argument("TPM command is too large");
    }
    Bytes result;
    result.reserve(static_cast<std::size_t>(size));
    PutU16(result, kTagSessions);
    PutU32(result, static_cast<std::uint32_t>(size));
    PutU32(result, command_code);
    result.insert(result.end(), body.begin(), body.end());
    return result;
}

Bytes ReadTpm2B(const Bytes& input, std::size_t& offset) {
    const auto size = GetU16(input, offset);
    if (offset + size > input.size()) throw std::invalid_argument("truncated TPM2B");
    Bytes result(input.begin() + static_cast<std::ptrdiff_t>(offset),
                 input.begin() + static_cast<std::ptrdiff_t>(offset + size));
    offset += size;
    return result;
}

} // namespace

Bytes BuildCommitCommand(const CommitParameters& parameters) {
    Bytes body;
    PutPoint(body, parameters.p1);
    PutTpm2B(body, parameters.s2);
    PutTpm2B(body, parameters.y2);
    return Finish(kCommandCommit, parameters.signing_key_handle, parameters.authorization, std::move(body));
}

Bytes BuildSignCommand(const SignParameters& parameters) {
    if (parameters.digest.empty()) throw std::invalid_argument("digest must not be empty");
    Bytes body;
    PutTpm2B(body, parameters.digest);
    PutU16(body, static_cast<std::uint16_t>(parameters.scheme));
    PutU16(body, parameters.hash_algorithm);
    if (parameters.scheme == SignatureScheme::Ecdaa) PutU16(body, parameters.commit_counter);
    // TPMT_TK_HASHCHECK: TPM_ST_HASHCHECK, hierarchy TPM_RH_NULL, empty digest.
    PutU16(body, 0x8024);
    PutU32(body, 0x40000007);
    PutU16(body, 0);
    return Finish(kCommandSign, parameters.key_handle, parameters.authorization, std::move(body));
}

TpmResponse ParseResponse(const Bytes& response) {
    if (response.size() < 10) throw std::invalid_argument("TPM response header is truncated");
    std::size_t offset = 0;
    TpmResponse parsed;
    parsed.tag = GetU16(response, offset);
    const auto declared_size = GetU32(response, offset);
    parsed.response_code = GetU32(response, offset);
    if (declared_size != response.size()) throw std::invalid_argument("TPM response size mismatch");
    if (parsed.response_code == 0 && parsed.tag == kTagSessions) {
        const auto parameter_size = GetU32(response, offset);
        if (offset + parameter_size > response.size()) {
            throw std::invalid_argument("TPM response parameter size mismatch");
        }
        parsed.parameters.assign(response.begin() + static_cast<std::ptrdiff_t>(offset),
                                 response.begin() + static_cast<std::ptrdiff_t>(offset + parameter_size));
    } else {
        parsed.parameters.assign(response.begin() + static_cast<std::ptrdiff_t>(offset), response.end());
    }
    return parsed;
}

Bytes ParseEccSignature(const TpmResponse& response) {
    if (response.response_code != 0) throw std::runtime_error("TPM command failed");
    std::size_t offset = 0;
    const auto scheme = GetU16(response.parameters, offset);
    if (scheme != static_cast<std::uint16_t>(SignatureScheme::Ecdsa) &&
        scheme != static_cast<std::uint16_t>(SignatureScheme::Ecdaa)) {
        throw std::invalid_argument("TPM response is not an ECC signature");
    }
    (void)GetU16(response.parameters, offset); // hash algorithm
    const auto r = ReadTpm2B(response.parameters, offset);
    const auto s = ReadTpm2B(response.parameters, offset);
    if (offset != response.parameters.size() || r.size() > 32 || s.size() > 32) {
        throw std::invalid_argument("invalid P-256 TPM signature encoding");
    }
    Bytes result(64, 0);
    std::copy(r.begin(), r.end(), result.begin() + static_cast<std::ptrdiff_t>(32 - r.size()));
    std::copy(s.begin(), s.end(), result.begin() + static_cast<std::ptrdiff_t>(64 - s.size()));
    return result;
}

} // namespace PromptKit::TPM2
