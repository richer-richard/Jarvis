import Foundation

public struct CommandResponse: Decodable, Sendable {
    public let command: String?
    public let tool: String?
    public let summary: String?
    public let result: JSONValue?
    public let executed: Bool?
    public let confirmation: Confirmation?
    public let assessment: SafetyAssessment?
    public let auditEventId: String?
    public let speech: JSONValue?
}

public struct SpeechStatusResponse: Decodable, Sendable {
    public let tool: String?
    public let status: String?
    public let executed: Bool?
    public let textLength: Int?
    public let speech: JSONValue?
}

public struct StreamStatusEvent: Decodable, Sendable {
    public let text: String
    public let tool: String?
    public let kind: String?
    public let replaceStreamingPreview: Bool?
    public let speech: JSONValue?
}

public struct SpeechMuteResponse: Decodable, Sendable {
    public let tool: String?
    public let status: String?
    public let executed: Bool?
    public let muted: Bool
    public let previousMuted: Bool?
    public let activeSpeech: Bool?
    public let interruptedPrevious: Bool?
    public let automaticTtsEnabled: Bool?
    public let statusSpeechEnabled: Bool?
    public let ttsProvider: String?
    public let ttsAvailable: Bool?
    public let automaticSpeechAvailable: Bool?
    public let ttsUnavailableReason: String?
    public let reply: String?
}

public struct Confirmation: Decodable, Sendable {
    public let required: Bool
    public let kind: String
    public let title: String
    public let message: String?
    public let exactPhrase: String?
    public let prototypeNote: String?
}

public struct SafetyAssessment: Decodable, Sendable {
    public let riskLevel: Int
    public let riskLabel: String
    public let decision: String
    public let requiresConfirmation: Bool
    public let requiresTypedConfirmation: Bool
    public let blocked: Bool
    public let reasons: [String]
}

public struct HealthResponse: Decodable, Sendable {
    public let ok: Bool
    public let status: SystemStatus
    public let mode: ModeResponse?
}

public struct SystemStatus: Decodable, Sendable {
    public let projectRoot: String
    public let python: String
    public let platform: String
    public let machine: String
    public let runtime: RuntimeStatus?
    public let app: AppIdentityStatus?
    public let timers: TimerStatus?
    public let codexJobs: CodexJobHealth?
    public let codex: CodexStatus
    public let fastModel: FastModelStatus?
}

public struct AppIdentityStatus: Decodable, Sendable {
    public let bundlePath: String?
    public let bundleId: String?
    public let version: String?
    public let build: String?
    public let workerSourceKind: String?
    public let workerLaunchVersion: String?
    public let workerLaunchBuild: String?
    public let workerLaunchBundleId: String?
    public let workerLaunchAppPath: String?
    public let workerLaunchIdentityAvailable: Bool?
    public let workerLaunchMatchesBundle: Bool?
}

public struct RuntimeStatus: Decodable, Sendable {
    public let pid: Int
    public let cwd: String
    public let startedAt: Double
    public let uptimeSeconds: Double
    public let source: String
}

public struct CodexStatus: Decodable, Sendable {
    public let path: String?
    public let version: String?
}

public struct TimerStatus: Decodable, Sendable {
    public let activeCount: Int?
}

public struct CodexJobHealth: Decodable, Sendable {
    public let trackedCount: Int?
    public let runningCount: Int?
    public let latestJobId: String?
    public let latestStatus: String?
}

public struct CodexActivityResponse: Decodable, Sendable {
    public let tool: String?
    public let status: String
    public let trackedCount: Int
    public let runningCount: Int
    public let latestJob: CodexActivityJob?
    public let jobs: [CodexActivityJob]
    public let reply: String?
}

public struct CodexActivityJob: Decodable, Identifiable, Sendable {
    public let jobId: String
    public let status: String?
    public let phase: String?
    public let model: String?
    public let promptSummary: String?
    public let startedAt: Double?
    public let completedAt: Double?
    public let lastActivityAt: Double?
    public let durationHuman: String?
    public let durationSeconds: Double?
    public let returncode: Int?
    public let commandPreview: String?
    public let cliTail: String?
    public let stdoutTail: String?
    public let stderrTail: String?
    public let conversationTail: String?
    public let replyTail: String?

    public var id: String {
        jobId
    }
}

public struct FastModelStatus: Decodable, Sendable {
    public let backend: String?
    public let model: String?
    public let available: Bool?
    public let fallbackEnabled: Bool?
    public let fallbackBackend: String?
    public let fallbackModel: String?
    public let timeoutSeconds: Int?
    public let maxTokens: Int?
    public let groqKeyConfigured: Bool?
    public let groqBaseUrl: String?
    public let ollamaPath: String?
    public let ollamaBaseUrl: String?
}

public struct AuditStatusResponse: Decodable, Sendable {
    public let path: String
    public let exists: Bool
    public let eventCount: Int
    public let unreadableLines: Int
    public let byteSize: Int
    public let byteSizeHuman: String
    public let retentionDays: Int
    public let maxBytes: Int
    public let maxBytesHuman: String
    public let oldestTimestamp: Double?
    public let newestTimestamp: Double?
    public let rawAudioOrScreenshots: String
}

public struct ModeResponse: Decodable, Sendable {
    public let paused: Bool
    public let reason: String
    public let updatedAt: Double
    public let commandsEnabled: Bool
    public let allowedWhilePaused: [String]
    public let auditEventId: String?
}

public struct ReadinessResponse: Decodable, Sendable {
    public let ok: Bool
    public let generatedAt: Double
    public let mode: ModeResponse
    public let worker: WorkerReadiness
    public let tools: ToolReadinessSummary
    public let selfCheck: SelfCheckSummary
    public let audit: AuditStatusResponse
    public let verification: VerificationSummary?
    public let notes: [String]
}

public struct WorkerReadiness: Decodable, Sendable {
    public let projectRoot: String
    public let platform: String
    public let python: String
    public let codexAvailable: Bool
    public let codexVersion: String?
    public let runtime: RuntimeStatus?
}

public struct ToolReadinessSummary: Decodable, Sendable {
    public let total: Int
    public let available: Int
    public let unavailableIds: [String]
}

public struct SelfCheckSummary: Decodable, Sendable {
    public let ok: Bool
    public let total: Int
    public let passed: Int
    public let failed: [String]
}

public struct VerificationSummary: Decodable, Sendable {
    public let available: Bool
    public let path: String?
    public let ok: Bool?
    public let passed: Int?
    public let total: Int?
    public let generatedAt: Double?
    public let ageSeconds: Double?
    public let ageHuman: String?
}

public struct PreflightResponse: Decodable, Sendable {
    public let ok: Bool
    public let generatedAt: Double
    public let mode: ModeResponse
    public let summary: PreflightSummary
    public let checks: [PreflightCheck]
    public let notes: [String]
}

public struct PreflightSummary: Decodable, Sendable {
    public let requiredTotal: Int
    public let requiredPassed: Int
    public let recommendedTotal: Int
    public let recommendedPassed: Int
}

public struct PreflightCheck: Decodable, Sendable {
    public let id: String
    public let label: String
    public let passed: Bool
    public let severity: String
    public let detail: String
}

public indirect enum JSONValue: Decodable, Sendable, Equatable {
    case string(String)
    case number(Double)
    case bool(Bool)
    case object([String: JSONValue])
    case array([JSONValue])
    case null

    public init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() {
            self = .null
        } else if let value = try? container.decode(Bool.self) {
            self = .bool(value)
        } else if let value = try? container.decode(Double.self) {
            self = .number(value)
        } else if let value = try? container.decode(String.self) {
            self = .string(value)
        } else if let value = try? container.decode([String: JSONValue].self) {
            self = .object(value)
        } else if let value = try? container.decode([JSONValue].self) {
            self = .array(value)
        } else {
            throw DecodingError.dataCorruptedError(in: container, debugDescription: "Unsupported JSON value")
        }
    }

    public var stringValue: String? {
        if case .string(let value) = self {
            return value
        }
        return nil
    }

    public var intValue: Int? {
        if case .number(let value) = self {
            return Int(value)
        }
        return nil
    }

    public var doubleValue: Double? {
        if case .number(let value) = self {
            return value
        }
        return nil
    }

    public var boolValue: Bool? {
        if case .bool(let value) = self {
            return value
        }
        return nil
    }

    public var objectValue: [String: JSONValue]? {
        if case .object(let value) = self {
            return value
        }
        return nil
    }

    public var arrayValue: [JSONValue]? {
        if case .array(let value) = self {
            return value
        }
        return nil
    }

    public var anyValue: Any {
        switch self {
        case .string(let value):
            return value
        case .number(let value):
            return value
        case .bool(let value):
            return value
        case .object(let value):
            return value.mapValues(\.anyValue)
        case .array(let value):
            return value.map(\.anyValue)
        case .null:
            return NSNull()
        }
    }
}
