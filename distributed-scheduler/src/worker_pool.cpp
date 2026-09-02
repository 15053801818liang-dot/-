#include "worker_pool.h"

void WorkerPool::add_or_update(const std::string& identity) {
    auto it = pool_.find(identity);
    if (it != pool_.end()) {
        it->second.last_heartbeat = clk::now();   // 存活刷新，不改 busy 状态
    } else {
        pool_.emplace(identity, WorkerNode{identity, clk::now(), false});
        idle_ids_.insert(identity);               // 新 worker 默认空闲
    }
}

bool WorkerPool::has_idle() const {
    return !idle_ids_.empty();                    // O(1)
}

std::optional<std::string> WorkerPool::find_and_mark_idle() {
    auto it = idle_ids_.begin();
    if (it == idle_ids_.end()) return std::nullopt;   // O(1)
    std::string id = *it;
    idle_ids_.erase(it);
    auto& node = pool_[id];
    node.busy = true;
    node.last_heartbeat = clk::now();
    return id;
}

void WorkerPool::mark_idle(const std::string& identity) {
    auto it = pool_.find(identity);
    if (it != pool_.end()) {
        it->second.busy = false;
        it->second.last_heartbeat = clk::now();
        idle_ids_.insert(identity);
    }
}

std::vector<std::string> WorkerPool::reap_stale_idle(clk::duration timeout) {
    std::vector<std::string> dead;
    auto now = clk::now();
    for (auto it = pool_.begin(); it != pool_.end(); ) {
        if (!it->second.busy && now - it->second.last_heartbeat > timeout) {
            idle_ids_.erase(it->first);
            dead.push_back(it->first);
            it = pool_.erase(it);
        } else {
            ++it;
        }
    }
    return dead;
}

std::vector<std::string> WorkerPool::reap_stale_busy(clk::duration timeout) {
    std::vector<std::string> dead;
    auto now = clk::now();
    for (auto it = pool_.begin(); it != pool_.end(); ) {
        if (it->second.busy && now - it->second.last_heartbeat > timeout) {
            idle_ids_.erase(it->first);            // 防御性：繁忙 worker 本不在集合中
            dead.push_back(it->first);
            it = pool_.erase(it);
        } else {
            ++it;
        }
    }
    return dead;
}

std::optional<WorkerNode> WorkerPool::get(const std::string& identity) const {
    auto it = pool_.find(identity);
    if (it != pool_.end()) return it->second;
    return std::nullopt;
}

size_t WorkerPool::size() const { return pool_.size(); }
