import Foundation
public struct YBLLMPersona: Sendable {
    public let traits: [String]
    public init(traits: [String]) { self.traits = traits }
    public func inject(into base: String) -> String { base + "\n性格特征：" + traits.joined(separator: "，") }
}
