#include "TPMCommandCodec.h"

#include <cassert>
#include <cstdint>
#include <stdexcept>

using namespace PromptKit::TPM2;

int main() {
    const auto sign = BuildSignCommand(SignParameters{
        0x81010002, Bytes(32, 0xA5), SignatureScheme::Ecdsa, kAlgSha256, 0, {}});
    assert(sign.size() == 73);
    assert(sign[0] == 0x80 && sign[1] == 0x02);
    assert(sign[6] == 0x00 && sign[7] == 0x00 && sign[8] == 0x01 && sign[9] == 0x5D);
    assert(sign[10] == 0x81 && sign[13] == 0x02);
    assert(sign[14] == 0x00 && sign[17] == 0x09); // auth area size
    assert(sign[27] == 0x00 && sign[28] == 0x20);

    const auto commit = BuildCommitCommand(CommitParameters{
        0x81010002, {}, EccPoint{{1, 2}, {3, 4}}, {5}, {6}});
    assert(commit[8] == 0x01 && commit[9] == 0x8B);
    assert(commit[27] == 0x00 && commit[28] == 0x08); // outer TPMS_ECC_POINT size

    Bytes raw_response{0x80, 0x01, 0, 0, 0, 22, 0, 0, 0, 0,
                       0x00, 0x18, 0x00, 0x0B,
                       0x00, 0x02, 0x01, 0x02,
                       0x00, 0x02, 0x03, 0x04};
    const auto parsed = ParseResponse(raw_response);
    const auto signature = ParseEccSignature(parsed);
    assert(signature.size() == 64);
    assert(signature[30] == 1 && signature[31] == 2);
    assert(signature[62] == 3 && signature[63] == 4);

    bool rejected = false;
    try { (void)ParseResponse(Bytes{0x80}); } catch (const std::invalid_argument&) { rejected = true; }
    assert(rejected);
}
