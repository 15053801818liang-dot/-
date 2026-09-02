import Foundation

public enum AnyCodable: Codable, Sendable {
    case bool(Bool), integer(Int), double(Double), string(String)
    case array([AnyCodable]), object([String: AnyCodable]), null

    public init(from decoder: Decoder) throws {
        let value = try decoder.singleValueContainer()
        if value.decodeNil() { self = .null }
        else if let item = try? value.decode(Bool.self) { self = .bool(item) }
        else if let item = try? value.decode(Int.self) { self = .integer(item) }
        else if let item = try? value.decode(Double.self) { self = .double(item) }
        else if let item = try? value.decode(String.self) { self = .string(item) }
        else if let item = try? value.decode([AnyCodable].self) { self = .array(item) }
        else { self = .object(try value.decode([String: AnyCodable].self)) }
    }
    public func encode(to encoder: Encoder) throws {
        var value = encoder.singleValueContainer()
        switch self {
        case .bool(let item): try value.encode(item)
        case .integer(let item): try value.encode(item)
        case .double(let item): try value.encode(item)
        case .string(let item): try value.encode(item)
        case .array(let item): try value.encode(item)
        case .object(let item): try value.encode(item)
        case .null: try value.encodeNil()
        }
    }
}

public enum AgentAction: Sendable {
    case tool(name: String, parameters: [String: AnyCodable])
    case answer(String)
}
