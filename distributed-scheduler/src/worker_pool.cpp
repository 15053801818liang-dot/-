#include "worker_pool.h"

void WorkerPool::add_or_update(const std::string& identity) {
    auto it = pool_.find(identity);
    if (it != pool_.end()) {
        it->second.last_heartbeat = clk::now();
    } else {
        pool_.emplace(identity, WorkerNode{identity, clk::now(), false});
    }
}

bool WorkerPool::has_idle() const {
    for (const auto& [_, node] : pool_) {
        if (!node.busy) return true;
    }
    return false;
}

std::optional<std::string> WorkerPool::find_and_mark_idle() {
    for (auto& [id, node] : pool_) {
        if (!node.busy) {
            node.busy = true;
            node.last_heartbeat = clk::now();
            return id;
        }
    }
    return std::nullopt;
}

void WorkerPool::mark_idle(const std::string& identity) {
    auto it = pool_.find(identity);
    if (it != pool_.end()) {
        it->second.busy = false;
        it->second.last_heartbeat = clk::now();
    }
}

std::vector<std::string> WorkerPool::reap_stale_idle(clk::duration timeout) {
    std::vector<std::string> dead;
    auto now = clk::now();
    for (auto it = pool_.begin(); it != pool_.end(); ) {
        if (!it->second.busy && now - it->second.last_heartbeat > timeout) {
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
