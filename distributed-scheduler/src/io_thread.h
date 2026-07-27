#pragma once
#include <vector>
#include <zmq.hpp>

void io_thread_main();
void send_to_io_thread(std::vector<zmq::message_t>&& frames);
