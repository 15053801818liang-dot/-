#pragma once

#include "TPMCommandCodec.h"

#include <cstdint>
#include <vector>

#ifdef _WIN32
#include <windows.h>
#include <tbs.h>
#endif

namespace PromptKit::Windows {

class TPMHelper final {
public:
    TPMHelper();
    ~TPMHelper();
    TPMHelper(const TPMHelper&) = delete;
    TPMHelper& operator=(const TPMHelper&) = delete;

    [[nodiscard]] bool IsAvailable() const noexcept;
    TPM2::TpmResponse Commit(const TPM2::CommitParameters& parameters) const;
    std::vector<std::uint8_t> Sign(const TPM2::SignParameters& parameters) const;

private:
    std::vector<std::uint8_t> Submit(const std::vector<std::uint8_t>& command) const;
#ifdef _WIN32
    TBS_HCONTEXT context_{0};
#endif
};

} // namespace PromptKit::Windows
