#pragma once

#include <stdexcept>
#include <string>
#include <utility>

// Unlike assert(), these checks remain active in Release/NDEBUG builds.
inline void Require(bool condition, const char* message) {
    if (!condition) throw std::runtime_error(message);
}

template<class Exception, class Function>
void ExpectThrows(Function&& operation, const char* message) {
    try {
        std::forward<Function>(operation)();
    } catch (const Exception&) {
        return;
    }
    throw std::runtime_error(message);
}
