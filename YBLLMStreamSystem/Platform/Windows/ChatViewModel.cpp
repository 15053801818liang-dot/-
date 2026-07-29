#include "ChatViewModel.h"

#ifdef _WIN32
#include <stdexcept>

namespace PromptKit::Windows {

ChatViewModel::ChatViewModel(std::shared_ptr<IChatCore> core,
    winrt::Microsoft::UI::Dispatching::DispatcherQueue dispatcher)
    : core_(std::move(core)), dispatcher_(std::move(dispatcher)) {
    if (!core_ || !dispatcher_) throw std::invalid_argument("chat core and dispatcher are required");
}

winrt::hstring ChatViewModel::Prompt() const { return prompt_; }
winrt::hstring ChatViewModel::Response() const { return response_; }
winrt::hstring ChatViewModel::ErrorMessage() const { return error_; }
bool ChatViewModel::IsBusy() const noexcept { return busy_; }
bool ChatViewModel::CanSend() const noexcept { return !busy_ && !prompt_.empty(); }

void ChatViewModel::Prompt(winrt::hstring const& value) {
    if (prompt_ == value) return;
    prompt_ = value;
    Notify(L"Prompt");
    Notify(L"CanSend");
}

void ChatViewModel::Send() {
    if (!CanSend()) return;
    busy_ = true;
    response_.clear();
    error_.clear();
    Notify(L"IsBusy"); Notify(L"CanSend"); Notify(L"Response"); Notify(L"ErrorMessage");
    auto weak = get_weak();
    core_->Stream(prompt_.c_str(),
        [weak](std::wstring_view token) {
            const std::wstring owned(token);
            if (auto self = weak.get()) self->Dispatch([weak, owned] {
                if (auto target = weak.get()) {
                    std::wstring combined{target->response_.c_str()};
                    combined.append(owned);
                    target->response_ = winrt::hstring{combined};
                    target->Notify(L"Response");
                }
            });
        },
        [weak](std::wstring_view message) {
            const winrt::hstring owned(message);
            if (auto self = weak.get()) self->Dispatch([weak, owned] {
                if (auto target = weak.get()) {
                    target->error_ = owned; target->busy_ = false;
                    target->Notify(L"ErrorMessage"); target->Notify(L"IsBusy"); target->Notify(L"CanSend");
                }
            });
        },
        [weak] {
            if (auto self = weak.get()) self->Dispatch([weak] {
                if (auto target = weak.get()) {
                    target->busy_ = false; target->Notify(L"IsBusy"); target->Notify(L"CanSend");
                }
            });
        });
}

void ChatViewModel::Cancel() noexcept {
    if (busy_) core_->Cancel();
}

void ChatViewModel::Dispatch(std::function<void()> action) {
    if (!dispatcher_.TryEnqueue(std::move(action))) {
        // The window is shutting down. Dropping the callback is safer than
        // mutating bindable state from a worker thread.
    }
}

void ChatViewModel::Notify(std::wstring_view name) {
    changed_(*this, winrt::Microsoft::UI::Xaml::Data::PropertyChangedEventArgs{winrt::hstring{name}});
}

winrt::event_token ChatViewModel::PropertyChanged(
    winrt::Microsoft::UI::Xaml::Data::PropertyChangedEventHandler const& handler) {
    return changed_.add(handler);
}
void ChatViewModel::PropertyChanged(winrt::event_token const& token) noexcept { changed_.remove(token); }

} // namespace PromptKit::Windows
#endif
