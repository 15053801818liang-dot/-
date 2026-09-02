import Foundation

/// Bridges the Objective-C delegate API to structured concurrency.
public final class YBLLMStructuredStreamService: @unchecked Sendable {
    public static let shared = YBLLMStructuredStreamService()
    private let manager = YBLLMMultiSessionStreamManager.shared()
    private let lock = NSLock()
    private var delegates: [String: StreamDelegate] = [:]
    private init() {}

    public func startStream(prompt: String, sessionId: String = UUID().uuidString) -> AsyncThrowingStream<String, Error> {
        AsyncThrowingStream { continuation in
            let delegate = StreamDelegate(
                onToken: { continuation.yield($0) },
                onFinish: { [weak self] in continuation.finish(); self?.remove(sessionId) },
                onError: { [weak self] in continuation.finish(throwing: $0); self?.remove(sessionId) }
            )
            lock.withLock { delegates[sessionId] = delegate }
            manager.startStream(forSession: sessionId, prompt: prompt, delegate: delegate)
            continuation.onTermination = { [weak self] _ in
                self?.manager.cancelStream(forSession: sessionId)
                self?.remove(sessionId)
            }
        }
    }

    private func remove(_ sessionId: String) { lock.withLock { delegates.removeValue(forKey: sessionId) } }

    private final class StreamDelegate: NSObject, YBLLMStreamDelegate {
        let onToken: @Sendable (String) -> Void
        let onFinish: @Sendable () -> Void
        let onError: @Sendable (Error) -> Void
        init(onToken: @escaping @Sendable (String) -> Void, onFinish: @escaping @Sendable () -> Void, onError: @escaping @Sendable (Error) -> Void) {
            self.onToken = onToken; self.onFinish = onFinish; self.onError = onError
        }
        func streamDidReceiveToken(_ token: String, forSession sessionId: String) { onToken(token) }
        func streamDidFinish(forSession sessionId: String) { onFinish() }
        func streamDidFailWithError(_ error: Error, forSession sessionId: String) { onError(error) }
    }
}
