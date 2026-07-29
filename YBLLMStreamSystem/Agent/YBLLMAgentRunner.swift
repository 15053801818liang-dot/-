import Foundation

public final class YBLLMAgentRunner: Sendable {
    public static let shared = YBLLMAgentRunner()
    private let streams = YBLLMStructuredStreamService.shared
    private let tools = YBLLMToolRegistry.shared
    private init() {}

    public func run(goal: String, environment: YBPromptEnvironment) -> AsyncThrowingStream<AgentStep, Error> {
        AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    var context = goal
                    for _ in 0..<10 {
                        var response = ""
                        for try await delta in streams.startStream(prompt: buildPrompt(context, environment: environment)) { response += delta }
                        let step = try parseStep(response)
                        continuation.yield(step)
                        switch step.action {
                        case .answer: continuation.finish(); return
                        case .tool(let name, let parameters):
                            let result = try await tools.call(name: name, parameters: parameters)
                            context += "\nObservation: \(result)"
                        case nil: continuation.finish(); return
                        }
                    }
                    throw RunnerError.maximumIterationsExceeded
                } catch is CancellationError {
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
            continuation.onTermination = { _ in task.cancel() }
        }
    }

    private func buildPrompt(_ context: String, environment: YBPromptEnvironment) -> String {
        """
        \(SystemPrompt.shared().prompt(forEnvironment: environment))
        Return one JSON object with thought and action fields.
        Context: \(context)
        """
    }

    private func parseStep(_ text: String) throws -> AgentStep {
        guard let data = text.data(using: .utf8),
              let object = try JSONSerialization.jsonObject(with: data) as? [String: Any],
              let thought = object["thought"] as? String,
              let action = object["action"] as? [String: Any],
              let type = action["type"] as? String else {
            // The bundled transport is deliberately a stub, so expose its text as a final answer.
            return AgentStep(thought: text, action: .answer(text))
        }
        if type == "answer", let answer = action["answer"] as? String {
            return AgentStep(thought: thought, action: .answer(answer))
        }
        guard type == "tool", let name = action["name"] as? String else { throw RunnerError.invalidAction }
        let parametersData = try JSONSerialization.data(withJSONObject: action["parameters"] as? [String: Any] ?? [:])
        let parameters = try JSONDecoder().decode([String: AnyCodable].self, from: parametersData)
        return AgentStep(thought: thought, action: .tool(name: name, parameters: parameters))
    }

    public enum RunnerError: LocalizedError {
        case invalidAction, maximumIterationsExceeded
        public var errorDescription: String? {
            switch self { case .invalidAction: "Invalid agent action"; case .maximumIterationsExceeded: "Maximum iterations exceeded" }
        }
    }
}
