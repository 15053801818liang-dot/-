cmake_minimum_required(VERSION 3.16)
project(distributed_scheduler LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release)
endif()

find_package(Threads REQUIRED)

# ZeroMQ: 优先 CMake config，退回 pkg-config
find_package(ZeroMQ QUIET)
if(NOT ZeroMQ_FOUND)
    find_package(PkgConfig REQUIRED)
    pkg_check_modules(ZMQ REQUIRED libzmq)
    set(ZMQ_LIBS ${ZMQ_LIBRARIES})
    set(ZMQ_INCS ${ZMQ_INCLUDE_DIRS})
else()
    set(ZMQ_LIBS libzmq)
    set(ZMQ_INCS "")
endif()

# nlohmann_json: 优先 CMake config，退回系统头文件
find_package(nlohmann_json 3 QUIET)

function(link_common target)
    target_include_directories(${target} PRIVATE src ${ZMQ_INCS})
    target_link_libraries(${target} PRIVATE ${ZMQ_LIBS} Threads::Threads)
    if(nlohmann_json_FOUND)
        target_link_libraries(${target} PRIVATE nlohmann_json::nlohmann_json)
    endif()
    if(WIN32)
        target_link_libraries(${target} PRIVATE ws2_32)
    endif()
endfunction()

# Hub 主程序
add_executable(hub
    src/hub.cpp
    src/io_thread.cpp
    src/scheduler.cpp
    src/wal.cpp
    src/worker_pool.cpp
)
link_common(hub)

# WAL 单元测试（不链接 hub.cpp，自带 g_state 定义）
add_executable(test_wal_replay
    tests/test_wal_replay.cpp
    src/wal.cpp
    src/worker_pool.cpp
)
link_common(test_wal_replay)

# 端到端压测客户端
add_executable(worker_bench
    src/worker_bench.cpp
)
link_common(worker_bench)

enable_testing()
add_test(NAME wal_replay COMMAND test_wal_replay)
