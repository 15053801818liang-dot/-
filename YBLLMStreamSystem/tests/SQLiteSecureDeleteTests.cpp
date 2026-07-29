#include "SQLiteSecureDelete.h"

#include <cassert>
#include <cstdint>
#include <filesystem>
#include <vector>

using PromptKit::Windows::SQLiteSecureDelete;

int main() {
    const auto path = std::filesystem::temp_directory_path() / "promptkit-secure-delete-test.sqlite3";
    std::filesystem::remove(path);
    {
        SQLiteSecureDelete store(path);
        const std::vector<std::uint8_t> secret{1, 2, 3, 4};
        store.Store("token", secret);
        assert(store.Load("token") == secret);
        assert(store.Delete("token"));
        assert(store.Load("token").empty());
        assert(!store.Delete("token"));
    }
    std::filesystem::remove(path);
}
