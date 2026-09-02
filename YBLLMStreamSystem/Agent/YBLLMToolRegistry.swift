import Foundation

public actor YBLLMToolRegistry {
    public static let shared = YBLLMToolRegistry()
    public typealias Handler = @Sendable ([String: AnyCodable]) async throws -> String
    private var tools: [String: Handler] = [:]
    private init() {}

    public func register(name: String, handler: @escaping Handler) { tools[name] = handler }
    public func call(name: String, parameters: [String: AnyCodable]) async throws -> String {
        guard let handler = tools[name] else { throw ToolError.notFound(name) }
        return try await handler(parameters)
    }
    public enum ToolError: LocalizedError {
        case notFound(String)
        public var errorDescription: String? {
            guard case .notFound(let name) = self else { return nil }
            return "Tool not found: \(name)"
        }
    }
}
