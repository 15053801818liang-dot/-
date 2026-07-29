import Foundation
public struct YBLLMContextCompressor: Sendable {
    public static let shared = YBLLMContextCompressor()
    private init() {}
    public func compress(_ text: String, maxCharacters: Int = 4096) -> String {
        guard text.count > maxCharacters else { return text }
        return String(text.suffix(max(0, maxCharacters))) + "… (保留最近内容)"
    }
    public func summarize(_ text: String) -> String {
        guard text.count > 200 else { return text }
        return String(text.prefix(200)) + "… (摘要)"
    }
}
