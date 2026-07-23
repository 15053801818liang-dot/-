#include "io_thread.h"
#include "shared_state.h"
#include "protocol.h"
#include "prof.h"
#include <chrono>

void send_to_io_thread(std::vector<zmq::message_t>&& frames) {
    ScopedProf _p(Prof::ZmqEnqueue);
    std::lock_guard<std::mutex> lock(g_io_ctx.send_mutex);
    g_io_ctx.send_queue.push_back(std::move(frames));
}

void io_thread_main() {
    zmq::pollitem_t items[] = {{ static_cast<void*>(g_io_ctx.router), 0, ZMQ_POLLIN, 0 }};

    while (g_io_ctx.running.load()) {
        // 1. 非阻塞发送（优先保证下行延迟）
        {
            std::lock_guard<std::mutex> lock(g_io_ctx.send_mutex);
            while (!g_io_ctx.send_queue.empty()) {
                auto& msg = g_io_ctx.send_queue.front();
                for (size_t i = 0; i < msg.size(); ++i) {
                    auto flags = (i + 1 == msg.size())
                                 ? zmq::send_flags::none
                                 : zmq::send_flags::sndmore;
                    g_io_ctx.router.send(msg[i], flags);
                }
                g_io_ctx.send_queue.pop_front();
            }
        }

        // 2. Poll（10ms 节拍，平衡延迟与 CPU）
        try {
            zmq::poll(items, 1, std::chrono::milliseconds(POLL_TIMEOUT_MS));
        } catch (const zmq::error_t& e) {
            // 客户端连接洪泛导致 FD 耗尽时，libzmq 内部丢弃新连接，
            // 已建立连接仍可服务；不因瞬时错误崩溃整个 Hub。
            if (e.num() == EINTR || e.num() == EAGAIN ||
                e.num() == EMFILE || e.num() == ENFILE) continue;
            throw;
        }

        if (!(items[0].revents & ZMQ_POLLIN)) continue;

        // 3. 非阻塞收取所有可读消息（原样入队，不解析）
        while (true) {
            zmq::message_t part;
            auto res = g_io_ctx.router.recv(part, zmq::recv_flags::dontwait);
            if (!res.has_value()) break;

            std::vector<zmq::message_t> frames;
            frames.push_back(std::move(part));        // frame 0: identity
            while (g_io_ctx.router.get(zmq::sockopt::rcvmore)) {
                zmq::message_t p;
                (void)g_io_ctx.router.recv(p, zmq::recv_flags::none);
                frames.push_back(std::move(p));       // delimiter?/payload...
            }

            {
                std::lock_guard<std::mutex> lock(g_state.mutex);
                g_state.recv_queue.push_back(std::move(frames));
            }
            g_state.cv.notify_one();
        }
    }
}
