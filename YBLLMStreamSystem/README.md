# YBLLMStreamSystem

An auditable iOS LLM streaming skeleton with explicit Core, Parsing, Agent,
Cognition, and UI boundaries. The included Core transport is a deterministic
stub; replace its token producer with the application's network client.

## Xcode integration

1. Add this directory to an iOS application target (iOS 16 or newer).
2. Set **Objective-C Bridging Header** to
   `YBLLMStreamSystem/Bridging/YBLLMBridgingHeader.h`.
3. Ensure every `.m` and `.swift` file is in **Compile Sources**.
4. Make `ChatViewController` the window's root view controller.

UIKit, QuartzCore, and Foundation are system frameworks; no package dependency
is required. Mutable shared Swift state uses actors or locks, while Objective-C
stores isolate mutations on private dispatch queues.
