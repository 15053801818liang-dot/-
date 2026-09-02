import Foundation
public struct AgentStep: Sendable {
    public let thought: String
    public let action: AgentAction?
    public let observation: String?
    public init(thought: String, action: AgentAction?, observation: String? = nil) {
        self.thought = thought; self.action = action; self.observation = observation
    }
}
