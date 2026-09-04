#include "TPMCommandCodec.h"

#include "TestSupport.h"
#include <cstdint>
#include <stdexcept>

using namespace PromptKit::TPM2;

int main() {
    const auto sign = BuildSignCommand(SignParameters{
        0x81010002, Bytes(32, 0xA5), SignatureScheme::Ecdsa, kAlgSha256, 0, {}});
    Require(sign.size() == 73, "sign command size");
    Require(sign[0] == 0x80 && sign[1] == 0x02, "sessions tag");
    Require(sign[6] == 0x00 && sign[7] == 0x00 && sign[8] == 0x01 && sign[9] == 0x5D, "sign command code");
    Require(sign[10] == 0x81 && sign[13] == 0x02, "key handle");
    Require(sign[14] == 0x00 && sign[17] == 0x09, "authorization area size");
    Require(sign[27] == 0x00 && sign[28] == 0x20, "digest size");

    const auto commit = BuildCommitCommand(CommitParameters{
        0x81010002, {}, EccPoint{{1, 2}, {3, 4}}, {5}, {6}});
    Require(commit[8] == 0x01 && commit[9] == 0x8B, "commit command code");
    Require(commit[27] == 0x00 && commit[28] == 0x08, "outer ECC point size");

    Bytes raw_response{0x80, 0x01, 0, 0, 0, 22, 0, 0, 0, 0,
                       0x00, 0x18, 0x00, 0x0B,
                       0x00, 0x02, 0x01, 0x02,
                       0x00, 0x02, 0x03, 0x04};
    const auto parsed = ParseResponse(raw_response);
    const auto signature = ParseEccSignature(parsed);
    Require(signature.size() == 64, "P-256 fixed signature size");
    Require(signature[30] == 1 && signature[31] == 2, "left-padded r");
    Require(signature[62] == 3 && signature[63] == 4, "left-padded s");

    for (std::size_t size = 0; size < raw_response.size(); ++size) {
        const Bytes truncated(raw_response.begin(), raw_response.begin() + size);
        ExpectThrows<std::invalid_argument>([&] { (void)ParseResponse(truncated); }, "truncated response accepted");
    }
    auto oversized = raw_response;
    oversized.push_back(0);
    ExpectThrows<std::invalid_argument>([&] { (void)ParseResponse(oversized); }, "trailing bytes accepted");
    const Bytes bad_parameters{0x80, 0x02, 0, 0, 0, 14, 0, 0, 0, 0, 0xff, 0xff, 0xff, 0xff};
    ExpectThrows<std::invalid_argument>([&] { (void)ParseResponse(bad_parameters); }, "oversized parameter area accepted");
    auto bad_signature = parsed;
    bad_signature.parameters.push_back(0);
    ExpectThrows<std::invalid_argument>([&] { (void)ParseEccSignature(bad_signature); }, "signature trailing bytes accepted");
    bad_signature = parsed;
    bad_signature.response_code = 0x101;
    ExpectThrows<std::runtime_error>([&] { (void)ParseEccSignature(bad_signature); }, "failed TPM response accepted");
    ExpectThrows<std::invalid_argument>([] { (void)BuildSignCommand(SignParameters{}); }, "empty digest accepted");
    SignParameters oversized_digest{};
    oversized_digest.digest.resize(65536, 1);
    ExpectThrows<std::invalid_argument>([&] { (void)BuildSignCommand(oversized_digest); }, "oversized TPM2B accepted");
}
