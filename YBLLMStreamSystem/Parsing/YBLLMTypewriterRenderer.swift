import Foundation

@MainActor
public final class YBLLMTypewriterRenderer {
    public static let shared = YBLLMTypewriterRenderer()
    public var onUpdate: ((String) -> Void)?
    private let buffer = YBLLMSentenceBuffer()
    private init() {}

    public func push(_ text: String, characterDelay: Duration = .milliseconds(20)) async {
        for character in text {
            buffer.appendToken(String(character))
            onUpdate?(buffer.visibleText)
            try? await Task.sleep(for: characterDelay)
        }
    }
    public func finish() { onUpdate?(buffer.visibleText) }
}
