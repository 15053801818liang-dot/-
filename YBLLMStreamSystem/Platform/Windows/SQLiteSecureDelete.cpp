#include "SQLiteSecureDelete.h"

#include <sqlite3.h>

#include <cstring>
#include <stdexcept>
#include <string>
#include <limits>
#ifdef _WIN32
#include <windows.h>
#endif

namespace PromptKit::Windows {
namespace {

class Statement final {
public:
    Statement(sqlite3* db, const char* sql) {
        if (sqlite3_prepare_v2(db, sql, -1, &value_, nullptr) != SQLITE_OK) {
            throw std::runtime_error(sqlite3_errmsg(db));
        }
    }
    ~Statement() { sqlite3_finalize(value_); }
    sqlite3_stmt* get() const noexcept { return value_; }
private:
    sqlite3_stmt* value_{nullptr};
};

void Wipe(void* data, std::size_t size) noexcept {
#if defined(_WIN32)
    SecureZeroMemory(data, size);
#elif defined(__STDC_LIB_EXT1__)
    (void)memset_s(data, size, 0, size);
#else
    volatile auto* cursor = static_cast<volatile unsigned char*>(data);
    while (size-- != 0) *cursor++ = 0;
#endif
}

void CheckBind(sqlite3* db, int result) {
    if (result != SQLITE_OK) throw std::runtime_error(sqlite3_errmsg(db));
}

} // namespace

SQLiteSecureDelete::SQLiteSecureDelete(const std::filesystem::path& path) {
    const auto utf8 = path.u8string();
    if (sqlite3_open_v2(reinterpret_cast<const char*>(utf8.c_str()), &database_,
                        SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE | SQLITE_OPEN_FULLMUTEX,
                        nullptr) != SQLITE_OK) {
        const std::string error = database_ ? sqlite3_errmsg(database_) : "sqlite open failed";
        if (database_) sqlite3_close_v2(database_);
        database_ = nullptr;
        throw std::runtime_error(error);
    }
    try {
        // `secure_delete=ON` overwrites deleted records before SQLite releases pages.
        // WAL is disabled because old frames would otherwise retain deleted values.
        Execute("PRAGMA secure_delete=ON;");
        Execute("PRAGMA journal_mode=DELETE;");
        Execute("CREATE TABLE IF NOT EXISTS secure_blobs("
                "key TEXT PRIMARY KEY NOT NULL, value BLOB NOT NULL) WITHOUT ROWID;");
    } catch (...) {
        sqlite3_close_v2(database_);
        database_ = nullptr;
        throw;
    }
}

SQLiteSecureDelete::~SQLiteSecureDelete() {
    if (database_) sqlite3_close_v2(database_);
}

void SQLiteSecureDelete::Execute(const char* sql) const {
    char* message = nullptr;
    const auto result = sqlite3_exec(database_, sql, nullptr, nullptr, &message);
    if (result != SQLITE_OK) {
        const std::string error = message ? message : sqlite3_errmsg(database_);
        sqlite3_free(message);
        throw std::runtime_error(error);
    }
}

void SQLiteSecureDelete::Store(std::string_view key, std::span<const std::uint8_t> value) {
    if (key.empty()) throw std::invalid_argument("secure storage key must not be empty");
    if (key.size() > static_cast<std::size_t>(std::numeric_limits<int>::max()) ||
        value.size() > static_cast<std::size_t>(std::numeric_limits<int>::max())) {
        throw std::invalid_argument("key or value exceeds SQLite binding limit");
    }
    Statement statement(database_,
        "INSERT INTO secure_blobs(key,value) VALUES(?1,?2) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value;");
    CheckBind(database_, sqlite3_bind_text(statement.get(), 1, key.data(),
                                            static_cast<int>(key.size()), SQLITE_TRANSIENT));
    CheckBind(database_, sqlite3_bind_blob(statement.get(), 2, value.data(),
                                            static_cast<int>(value.size()), SQLITE_TRANSIENT));
    if (sqlite3_step(statement.get()) != SQLITE_DONE) throw std::runtime_error(sqlite3_errmsg(database_));
}

std::vector<std::uint8_t> SQLiteSecureDelete::Load(std::string_view key) const {
    Statement statement(database_, "SELECT value FROM secure_blobs WHERE key=?1;");
    CheckBind(database_, sqlite3_bind_text(statement.get(), 1, key.data(),
                                            static_cast<int>(key.size()), SQLITE_TRANSIENT));
    const auto result = sqlite3_step(statement.get());
    if (result == SQLITE_DONE) return {};
    if (result != SQLITE_ROW) throw std::runtime_error(sqlite3_errmsg(database_));
    const auto size = sqlite3_column_bytes(statement.get(), 0);
    const auto* bytes = static_cast<const std::uint8_t*>(sqlite3_column_blob(statement.get(), 0));
    return size == 0 ? std::vector<std::uint8_t>{} : std::vector<std::uint8_t>(bytes, bytes + size);
}

bool SQLiteSecureDelete::Delete(std::string_view key) {
    // Keep a private copy so caller-owned key memory is not modified.
    std::vector<char> key_copy(key.begin(), key.end());
    try {
        Statement statement(database_, "DELETE FROM secure_blobs WHERE key=?1;");
        CheckBind(database_, sqlite3_bind_text(statement.get(), 1, key_copy.data(),
                                                static_cast<int>(key_copy.size()), SQLITE_TRANSIENT));
        if (sqlite3_step(statement.get()) != SQLITE_DONE) throw std::runtime_error(sqlite3_errmsg(database_));
        const bool removed = sqlite3_changes(database_) != 0;
        Wipe(key_copy.data(), key_copy.size());
        return removed;
    } catch (...) {
        Wipe(key_copy.data(), key_copy.size());
        throw;
    }
}

} // namespace PromptKit::Windows
