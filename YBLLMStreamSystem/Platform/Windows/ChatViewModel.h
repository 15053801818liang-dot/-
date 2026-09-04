#pragma once

#ifdef _WIN32
#include <winrt/Microsoft.UI.Dispatching.h>
#include <winrt/Microsoft.UI.Xaml.Data.h>
#include <winrt/Windows.Foundation.h>

#include <functional>
#include <memory>
#include <string_view>

namespace PromptKit::Windows {

class IChatCore {
public:
    virtual ~IChatCore() = default;
    virtual void Stream(std::wstring_view prompt,
                        std::function<void(std::wstring_view)> on_token,
                        std::function<void(std::wstring_view)> on_error,
                        std::function<void()> on_complete) = 0;
    virtual void Cancel() noexcept = 0;
};

struct ChatViewModel final : winrt::implements<ChatViewModel,
    winrt::Microsoft::UI::Xaml::Data::INotifyPropertyChanged> {
    ChatViewModel(std::shared_ptr<IChatCore> core,
                  winrt::Microsoft::UI::Dispatching::DispatcherQueue dispatcher);

    winrt::hstring Prompt() const;
    void Prompt(winrt::hstring const& value);
    winrt::hstring Response() const;
    winrt::hstring ErrorMessage() const;
    bool IsBusy() const noexcept;
    bool CanSend() const noexcept;
    void Send();
    void Cancel() noexcept;

    winrt::event_token PropertyChanged(
        winrt::Microsoft::UI::Xaml::Data::PropertyChangedEventHandler const& handler);
    void PropertyChanged(winrt::event_token const& token) noexcept;

private:
    void Notify(std::wstring_view name);
    void Dispatch(std::function<void()> action);
    std::shared_ptr<IChatCore> core_;
    winrt::Microsoft::UI::Dispatching::DispatcherQueue dispatcher_{nullptr};
    winrt::hstring prompt_;
    winrt::hstring response_;
    winrt::hstring error_;
    bool busy_{false};
    winrt::event<winrt::Microsoft::UI::Xaml::Data::PropertyChangedEventHandler> changed_;
};

} // namespace PromptKit::Windows
#endif
