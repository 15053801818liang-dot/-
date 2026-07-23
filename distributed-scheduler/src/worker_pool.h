#pragma once
#include <string>
#include <vector>
#include <chrono>
#include <cstdint>
#include <unordered_map>
#include <unordered_set>
#include <optional>
#include "worker_node.h"

// 所有方法均为无锁：调用方必须持有全局 g_state.mutex。
class WorkerPool {
public:
    void add_or_update(const std::string& identity);
    bool has_idle() const;
    std::optional<std::string> find_and_mark_idle();
    void mark_idle(const std::string& identity);

    // 超时回收（区分空闲 / 繁忙 Worker）
    std::vector<std::string> reap_stale_idle(clk::duration timeout);
    std::vector<std::string> reap_stale_busy(clk::duration timeout);

    std::optional<WorkerNode> get(const std::string& identity) const;
    size_t size() const;

private:
    std::unordered_map<std::string, WorkerNode> pool_;
    // 不变量: id ∈ idle_ids_  ⟺  pool_[id] 存在且 busy==false。
    // 使 has_idle()/find_and_mark_idle() 由 O(n) 降为 O(1)。
    std::unordered_set<std::string> idle_ids_;
};
