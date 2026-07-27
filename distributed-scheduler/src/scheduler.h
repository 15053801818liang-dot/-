#pragma once
#include <vector>
#include <zmq.hpp>

void scheduler_thread();
void worker_watchdog_thread();
void dispatch_message(std::vector<zmq::message_t>& frames);
