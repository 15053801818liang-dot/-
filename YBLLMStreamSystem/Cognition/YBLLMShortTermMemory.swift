import Foundation

public actor YBLLMShortTermMemory {
    public static let shared = YBLLMShortTermMemory()
    private var facts: [String] = []
    private init() {}
    public func remember(_ fact: String) { facts.append(fact) }
    public func summarize() -> String { facts.joined(separator: "\n") }
    public func clear() { facts.removeAll() }
}
