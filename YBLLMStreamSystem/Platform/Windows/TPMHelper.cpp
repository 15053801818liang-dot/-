#include "TPMHelper.h"

#include <stdexcept>
#include <string>

namespace PromptKit::Windows {

TPMHelper::TPMHelper() {
#ifdef _WIN32
    TBS_CONTEXT_PARAMS2 params{};
    params.version = TBS_CONTEXT_VERSION_TWO;
    params.includeTpm20 = 1;
    const auto status = Tbsi_Context_Create(reinterpret_cast<PCTBS_CONTEXT_PARAMS>(&params), &context_);
    if (status != TBS_SUCCESS) context_ = 0;
#endif
}

TPMHelper::~TPMHelper() {
#ifdef _WIN32
    if (context_ != 0) Tbsip_Context_Close(context_);
#endif
}

bool TPMHelper::IsAvailable() const noexcept {
#ifdef _WIN32
    return context_ != 0;
#else
    return false;
#endif
}

std::vector<std::uint8_t> TPMHelper::Submit(const std::vector<std::uint8_t>& command) const {
#ifdef _WIN32
    if (!IsAvailable()) throw std::runtime_error("TPM 2.0 TBS context is unavailable");
    std::vector<std::uint8_t> response(4096);
    UINT32 response_size = static_cast<UINT32>(response.size());
    const auto status = Tbsip_Submit_Command(context_, TBS_COMMAND_LOCALITY_ZERO,
                                             TBS_COMMAND_PRIORITY_NORMAL, command.data(),
                                             static_cast<UINT32>(command.size()), response.data(),
                                             &response_size);
    if (status != TBS_SUCCESS) {
        throw std::runtime_error("Tbsip_Submit_Command failed: " + std::to_string(status));
    }
    response.resize(response_size);
    return response;
#else
    (void)command;
    throw std::runtime_error("TPM submission is only supported on Windows");
#endif
}

TPM2::TpmResponse TPMHelper::Commit(const TPM2::CommitParameters& parameters) const {
    return TPM2::ParseResponse(Submit(TPM2::BuildCommitCommand(parameters)));
}

std::vector<std::uint8_t> TPMHelper::Sign(const TPM2::SignParameters& parameters) const {
    return TPM2::ParseEccSignature(TPM2::ParseResponse(Submit(TPM2::BuildSignCommand(parameters))));
}

} // namespace PromptKit::Windows
