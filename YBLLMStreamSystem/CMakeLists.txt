cmake_minimum_required(VERSION 3.20)
project(PromptKitWindowsCore LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

add_library(promptkit_tpm_codec Shared/src/TPMCommandCodec.cpp)
target_include_directories(promptkit_tpm_codec PUBLIC Shared/include)

add_executable(tpm_codec_tests tests/TPMCommandCodecTests.cpp)
target_link_libraries(tpm_codec_tests PRIVATE promptkit_tpm_codec)

find_package(SQLite3 REQUIRED)
add_library(promptkit_secure_delete Platform/Windows/SQLiteSecureDelete.cpp)
target_include_directories(promptkit_secure_delete PUBLIC Platform/Windows)
target_link_libraries(promptkit_secure_delete PUBLIC SQLite::SQLite3)

add_executable(sqlite_secure_delete_tests tests/SQLiteSecureDeleteTests.cpp)
target_link_libraries(sqlite_secure_delete_tests PRIVATE promptkit_secure_delete)

if(WIN32)
    add_library(promptkit_tpm Platform/Windows/TPMHelper.cpp)
    target_include_directories(promptkit_tpm PUBLIC Platform/Windows Shared/include)
    target_link_libraries(promptkit_tpm PUBLIC promptkit_tpm_codec tbs)
endif()

enable_testing()
add_test(NAME tpm_codec_tests COMMAND tpm_codec_tests)
add_test(NAME sqlite_secure_delete_tests COMMAND sqlite_secure_delete_tests)
