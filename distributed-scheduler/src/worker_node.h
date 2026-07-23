#pragma once
#include <string>
#include <chrono>

using clk = std::chrono::steady_clock;

struct WorkerNode {
    std::string    identity;
    clk::time_point last_heartbeat;
    bool           busy{false};
};
