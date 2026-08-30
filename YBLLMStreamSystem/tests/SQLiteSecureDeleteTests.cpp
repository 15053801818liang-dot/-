#include "SQLiteSecureDelete.h"

#include "TestSupport.h"
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <random>
#include <string>
#include <vector>

using PromptKit::Windows::SQLiteSecureDelete;

int main() {
    const auto temp_root = std::filesystem::canonical(std::filesystem::temp_directory_path());
    std::filesystem::path directory;
    std::random_device random;
    for (int attempt = 0; attempt < 100; ++attempt) {
        const auto candidate = temp_root / ("promptkit-test-" + std::to_string(random()));
        if (std::filesystem::create_directory(candidate)) {
            directory = candidate;
            break;
        }
    }
    Require(!directory.empty(), "could not allocate an exclusive test directory");
    const auto path = directory / "store.sqlite3";
    // No fixed-name pre-delete and no recursive removal of user data.
    const std::string marker(512, 'Z');
    const std::vector<std::uint8_t> secret(marker.begin(), marker.end());
    {
        SQLiteSecureDelete store(path);
        store.Store("token", secret);
        Require(store.Load("token") == secret, "stored value differs");
        const std::string injection = "'; DROP TABLE secure_blobs; --";
        store.Store(injection, {secret.data(), 4});
        Require(store.Load(injection).size() == 4, "key was interpreted as SQL");
        Require(store.Load("token") == secret, "unrelated value changed");
        ExpectThrows<std::invalid_argument>([&] { store.Store("", secret); }, "empty key accepted");
        Require(store.Delete(injection), "literal SQL-shaped key not removed");
    }
    {
        SQLiteSecureDelete store(path);
        Require(store.Load("token") == secret, "value did not survive reopen");
        Require(store.Delete("token"), "existing key not removed");
        Require(store.Load("token").empty(), "deleted key is readable");
        Require(!store.Delete("token"), "missing key reported removed");
    }
    {
        std::ifstream file(path, std::ios::binary);
        Require(file.good(), "cannot inspect database bytes");
        const std::string bytes((std::istreambuf_iterator<char>(file)), {});
        Require(bytes.find(marker) == std::string::npos, "deleted marker remains in database file");
    }
    Require(!std::filesystem::exists(path.string() + "-wal"), "unexpected WAL remains");
    Require(!std::filesystem::exists(path.string() + "-journal"), "unexpected journal remains");
    Require(directory.parent_path() == temp_root, "cleanup target left test root");
    Require(std::filesystem::remove(path), "test database cleanup failed");
    Require(std::filesystem::remove(directory), "test directory cleanup failed");
}
