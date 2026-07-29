#pragma once

#include <cstdint>
#include <filesystem>
#include <span>
#include <string_view>
#include <vector>

struct sqlite3;

namespace PromptKit::Windows {

class SQLiteSecureDelete final {
public:
    explicit SQLiteSecureDelete(const std::filesystem::path& path);
    ~SQLiteSecureDelete();
    SQLiteSecureDelete(const SQLiteSecureDelete&) = delete;
    SQLiteSecureDelete& operator=(const SQLiteSecureDelete&) = delete;

    void Store(std::string_view key, std::span<const std::uint8_t> value);
    [[nodiscard]] std::vector<std::uint8_t> Load(std::string_view key) const;
    [[nodiscard]] bool Delete(std::string_view key);

private:
    void Execute(const char* sql) const;
    sqlite3* database_{nullptr};
};

} // namespace PromptKit::Windows
