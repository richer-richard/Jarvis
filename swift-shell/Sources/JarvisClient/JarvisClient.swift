import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

public struct JarvisClient: Sendable {
    public let baseURL: URL
    public let commandURL: URL
    private static let commandTimeout: TimeInterval = 240
    private static let planTimeout: TimeInterval = 20
    private static let quickTimeout: TimeInterval = 10
    private static let readinessTimeout: TimeInterval = 20
    private static let nativeOCRTimeout: TimeInterval = 30

    public init(baseURL: URL) {
        self.baseURL = baseURL
        self.commandURL = baseURL
            .appendingPathComponent("api")
            .appendingPathComponent("command")
    }

    public init(commandURL: URL) {
        self.commandURL = commandURL
        self.baseURL = commandURL.deletingLastPathComponent().deletingLastPathComponent()
    }

    public static func fromEnvironment() throws -> JarvisClient {
        let environment = ProcessInfo.processInfo.environment
        if let urlString = environment["JARVIS_URL"] {
            guard let rawURL = URL(string: urlString) else {
                throw JarvisClientError.invalidURL(urlString)
            }
            let url = normalizedURL(rawURL)
            guard isLoopbackURL(url) else {
                throw JarvisClientError.nonLoopbackURL(url.absoluteString)
            }
            if isCommandEndpoint(url) {
                return JarvisClient(commandURL: url)
            }
            return JarvisClient(baseURL: url)
        }
        let baseURLString = environment["JARVIS_BASE_URL"] ?? "http://127.0.0.1:8765"
        guard let rawBaseURL = URL(string: baseURLString) else {
            throw JarvisClientError.invalidURL(baseURLString)
        }
        let baseURL = normalizedURL(rawBaseURL)
        guard isLoopbackURL(baseURL) else {
            throw JarvisClientError.nonLoopbackURL(baseURL.absoluteString)
        }
        if isCommandEndpoint(baseURL) {
            return JarvisClient(commandURL: baseURL)
        }
        return JarvisClient(baseURL: baseURL)
    }

    private static func normalizedURL(_ url: URL) -> URL {
        var value = url.absoluteString
        while value.hasSuffix("/") {
            value.removeLast()
        }
        return URL(string: value) ?? url
    }

    private static func isCommandEndpoint(_ url: URL) -> Bool {
        url.path.trimmingCharacters(in: CharacterSet(charactersIn: "/")).hasSuffix("api/command")
    }

    public static func isLoopbackURL(_ url: URL) -> Bool {
        guard url.scheme?.lowercased() == "http",
              let host = url.host?.lowercased() else {
            return false
        }
        return host == "localhost" || host == "127.0.0.1" || host == "::1"
    }

    public func send(command: String, history: [[String: String]] = []) async throws -> CommandResponse {
        var request = URLRequest(url: commandURL)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.timeoutInterval = Self.commandTimeout
        request.httpBody = try Self.commandBody(command: command, history: history)
        return try await perform(request, as: CommandResponse.self)
    }

    public func sendStreaming(
        command: String,
        history: [[String: String]] = [],
        onStatus: @escaping @MainActor (StreamStatusEvent) -> Void = { _ in },
        onDelta: @escaping @MainActor (String) -> Void
    ) async throws -> CommandResponse {
        let url = baseURL
            .appendingPathComponent("api")
            .appendingPathComponent("command")
            .appendingPathComponent("stream")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.timeoutInterval = Self.commandTimeout
        request.httpBody = try Self.commandBody(command: command, history: history)

        let (bytes, response) = try await URLSession.shared.bytes(for: request)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw JarvisClientError.missingResponse
        }
        guard 200..<300 ~= httpResponse.statusCode else {
            throw JarvisClientError.httpStatus(httpResponse.statusCode, "")
        }

        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        var eventName = "message"
        var dataLines: [String] = []
        var finalResponse: CommandResponse?

        func processEvent() async throws {
            guard !dataLines.isEmpty else {
                return
            }
            let payload = dataLines.joined(separator: "\n")
            guard let data = payload.data(using: .utf8) else {
                return
            }
            if eventName == "delta" {
                if let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                   let text = object["text"] as? String,
                   !text.isEmpty {
                    await onDelta(text)
                }
            } else if eventName == "status" {
                if let status = try? decoder.decode(StreamStatusEvent.self, from: data),
                   !status.text.isEmpty {
                    await onStatus(status)
                } else if let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                          let text = object["text"] as? String,
                          !text.isEmpty {
                    await onStatus(
                        StreamStatusEvent(
                            text: text,
                            tool: object["tool"] as? String,
                            kind: object["kind"] as? String,
                            replaceStreamingPreview: object["replaceStreamingPreview"] as? Bool,
                            speech: nil
                        )
                    )
                }
            } else if eventName == "final" {
                finalResponse = try decoder.decode(CommandResponse.self, from: data)
            }
        }

        for try await line in bytes.lines {
            let trimmedLine = line.trimmingCharacters(in: .whitespacesAndNewlines)
            if trimmedLine.isEmpty {
                try await processEvent()
                eventName = "message"
                dataLines.removeAll(keepingCapacity: true)
                continue
            }
            if trimmedLine.hasPrefix("event:") {
                if !dataLines.isEmpty {
                    try await processEvent()
                    dataLines.removeAll(keepingCapacity: true)
                }
                eventName = String(trimmedLine.dropFirst(6)).trimmingCharacters(in: .whitespaces)
            } else if trimmedLine.hasPrefix("data:") {
                dataLines.append(String(trimmedLine.dropFirst(5)).trimmingCharacters(in: .whitespaces))
            }
        }
        if !dataLines.isEmpty {
            try await processEvent()
        }
        guard let finalResponse else {
            throw JarvisClientError.streamMissingFinal
        }
        return finalResponse
    }

    public func plan(command: String) async throws -> CommandResponse {
        let url = baseURL
            .appendingPathComponent("api")
            .appendingPathComponent("plan")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.timeoutInterval = Self.planTimeout
        request.httpBody = try JSONSerialization.data(withJSONObject: ["command": command], options: [])
        return try await perform(request, as: CommandResponse.self)
    }

    public func stopSpeaking() async throws -> CommandResponse {
        var request = URLRequest(url: commandURL)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.timeoutInterval = Self.quickTimeout
        request.httpBody = try JSONSerialization.data(
            withJSONObject: ["command": "stop talking", "suppress_speech": true],
            options: []
        )
        return try await perform(request, as: CommandResponse.self)
    }

    public func stopMusic() async throws -> CommandResponse {
        var request = URLRequest(url: commandURL)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.timeoutInterval = Self.quickTimeout
        request.httpBody = try JSONSerialization.data(
            withJSONObject: ["command": "stop the music", "suppress_speech": true],
            options: []
        )
        return try await perform(request, as: CommandResponse.self)
    }

    public func unmuteSystemAudio() async throws -> CommandResponse {
        var request = URLRequest(url: commandURL)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.timeoutInterval = Self.quickTimeout
        request.httpBody = try JSONSerialization.data(
            withJSONObject: ["command": "unmute system audio", "suppress_speech": true],
            options: []
        )
        return try await perform(request, as: CommandResponse.self)
    }

    private static func commandBody(command: String, history: [[String: String]]) throws -> Data {
        var payload: [String: Any] = ["command": command]
        if !history.isEmpty {
            payload["history"] = history
        }
        return try JSONSerialization.data(withJSONObject: payload, options: [])
    }

    public func health() async throws -> HealthResponse {
        try await get(["api", "health"], as: HealthResponse.self)
    }

    public func auditStatus() async throws -> AuditStatusResponse {
        try await get(["api", "audit", "status"], as: AuditStatusResponse.self)
    }

    public func readiness() async throws -> ReadinessResponse {
        try await get(["api", "readiness"], timeout: Self.readinessTimeout, as: ReadinessResponse.self)
    }

    public func preflight() async throws -> PreflightResponse {
        try await get(["api", "preflight"], timeout: Self.readinessTimeout, as: PreflightResponse.self)
    }

    public func codexActivity() async throws -> CodexActivityResponse {
        try await get(["api", "codex", "activity"], as: CodexActivityResponse.self)
    }

    public func mode() async throws -> ModeResponse {
        try await get(["api", "mode"], as: ModeResponse.self)
    }

    public func setPaused(_ paused: Bool, reason: String = "") async throws -> ModeResponse {
        let url = baseURL
            .appendingPathComponent("api")
            .appendingPathComponent("mode")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.timeoutInterval = Self.quickTimeout
        request.httpBody = try JSONSerialization.data(
            withJSONObject: ["paused": paused, "reason": reason],
            options: []
        )
        return try await perform(request, as: ModeResponse.self)
    }

    public func summarizeVisibleOutlookText(
        command: String,
        text: String,
        diagnostics: VisibleOutlookTextDiagnostics
    ) async throws -> CommandResponse {
        let url = baseURL
            .appendingPathComponent("api")
            .appendingPathComponent("outlook")
            .appendingPathComponent("visible-text")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.timeoutInterval = Self.nativeOCRTimeout
        request.httpBody = try JSONSerialization.data(
            withJSONObject: [
                "command": command,
                "text": String(text.prefix(12_000)),
                "diagnostics": diagnostics.jsonObject,
            ],
            options: []
        )
        return try await perform(request, as: CommandResponse.self)
    }

    public func summarizeVisibleScreenText(
        command: String,
        text: String,
        diagnostics: VisibleOutlookTextDiagnostics
    ) async throws -> CommandResponse {
        let url = baseURL
            .appendingPathComponent("api")
            .appendingPathComponent("screen")
            .appendingPathComponent("visible-text")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.timeoutInterval = Self.nativeOCRTimeout
        request.httpBody = try JSONSerialization.data(
            withJSONObject: [
                "command": command,
                "text": String(text.prefix(12_000)),
                "diagnostics": diagnostics.jsonObject,
            ],
            options: []
        )
        return try await perform(request, as: CommandResponse.self)
    }

    public func readChromeActivePage(
        command: String,
        maxChars: Int = 6000,
        suppressSpeech: Bool = false
    ) async throws -> CommandResponse {
        let url = baseURL
            .appendingPathComponent("api")
            .appendingPathComponent("browser")
            .appendingPathComponent("read-page")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.timeoutInterval = Self.nativeOCRTimeout
        request.httpBody = try JSONSerialization.data(
            withJSONObject: [
                "command": command,
                "max_chars": max(1, maxChars),
                "suppress_speech": suppressSpeech,
            ],
            options: []
        )
        return try await perform(request, as: CommandResponse.self)
    }

    public func speakStatus(_ text: String) async throws -> SpeechStatusResponse {
        let url = baseURL
            .appendingPathComponent("api")
            .appendingPathComponent("speech")
            .appendingPathComponent("status")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.timeoutInterval = Self.quickTimeout
        request.httpBody = try JSONSerialization.data(
            withJSONObject: ["text": String(text.prefix(500))],
            options: []
        )
        return try await perform(request, as: SpeechStatusResponse.self)
    }

    public func speechMuteStatus() async throws -> SpeechMuteResponse {
        try await get(["api", "speech", "mute"], as: SpeechMuteResponse.self)
    }

    public func speechPlaying() async throws -> SpeechPlayingResponse {
        try await get(["api", "speech", "playing"], as: SpeechPlayingResponse.self)
    }

    public func setSpeechMuted(_ muted: Bool, source: String = "main_app") async throws -> SpeechMuteResponse {
        let url = baseURL
            .appendingPathComponent("api")
            .appendingPathComponent("speech")
            .appendingPathComponent("mute")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.timeoutInterval = Self.quickTimeout
        request.httpBody = try JSONSerialization.data(
            withJSONObject: ["muted": muted, "source": source],
            options: []
        )
        return try await perform(request, as: SpeechMuteResponse.self)
    }

    private func get<T: Decodable>(_ path: [String], timeout: TimeInterval = Self.quickTimeout, as type: T.Type) async throws -> T {
        let url = path.reduce(baseURL) { partial, component in
            partial.appendingPathComponent(component)
        }
        var request = URLRequest(url: url)
        request.timeoutInterval = timeout
        return try await perform(request, as: type)
    }

    private func perform<T: Decodable>(_ request: URLRequest, as type: T.Type) async throws -> T {
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw JarvisClientError.missingResponse
        }
        guard 200..<300 ~= httpResponse.statusCode else {
            throw JarvisClientError.httpStatus(
                httpResponse.statusCode,
                String(data: data, encoding: .utf8) ?? ""
            )
        }

        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(type, from: data)
    }
}

public struct VisibleOutlookTextDiagnostics: Sendable {
    public let source: String
    public let ocrEngine: String
    public let lineCount: Int
    public let characterCount: Int
    public let captureWidth: Int
    public let captureHeight: Int
    public let captureBoundsX: Double
    public let captureBoundsY: Double
    public let captureBoundsWidth: Double
    public let captureBoundsHeight: Double
    public let captureScaleX: Double
    public let captureScaleY: Double
    public let screenAccessPreflight: Bool
    public let captureError: String?
    public let captureMethod: String
    public let appBundlePath: String
    public let appExecutablePath: String
    public let bundleIdentifier: String
    public let targetAppName: String
    public let windowTitle: String

    public init(
        source: String = "native_vision_ocr",
        ocrEngine: String = "apple_vision",
        lineCount: Int = 0,
        characterCount: Int = 0,
        captureWidth: Int = 0,
        captureHeight: Int = 0,
        captureBoundsX: Double = 0,
        captureBoundsY: Double = 0,
        captureBoundsWidth: Double = 0,
        captureBoundsHeight: Double = 0,
        captureScaleX: Double = 0,
        captureScaleY: Double = 0,
        screenAccessPreflight: Bool = false,
        captureError: String? = nil,
        captureMethod: String = "",
        appBundlePath: String = "",
        appExecutablePath: String = "",
        bundleIdentifier: String = "",
        targetAppName: String = "",
        windowTitle: String = ""
    ) {
        self.source = source
        self.ocrEngine = ocrEngine
        self.lineCount = lineCount
        self.characterCount = characterCount
        self.captureWidth = captureWidth
        self.captureHeight = captureHeight
        self.captureBoundsX = captureBoundsX
        self.captureBoundsY = captureBoundsY
        self.captureBoundsWidth = captureBoundsWidth
        self.captureBoundsHeight = captureBoundsHeight
        self.captureScaleX = captureScaleX
        self.captureScaleY = captureScaleY
        self.screenAccessPreflight = screenAccessPreflight
        self.captureError = captureError
        self.captureMethod = captureMethod
        self.appBundlePath = appBundlePath
        self.appExecutablePath = appExecutablePath
        self.bundleIdentifier = bundleIdentifier
        self.targetAppName = targetAppName
        self.windowTitle = windowTitle
    }

    public var jsonObject: [String: Any] {
        var value: [String: Any] = [
            "source": source,
            "ocr_engine": ocrEngine,
            "line_count": lineCount,
            "character_count": characterCount,
            "capture_width": captureWidth,
            "capture_height": captureHeight,
            "capture_bounds_x": captureBoundsX,
            "capture_bounds_y": captureBoundsY,
            "capture_bounds_width": captureBoundsWidth,
            "capture_bounds_height": captureBoundsHeight,
            "capture_scale_x": captureScaleX,
            "capture_scale_y": captureScaleY,
            "screen_access_preflight": screenAccessPreflight,
        ]
        if let captureError, !captureError.isEmpty {
            value["capture_error"] = captureError
        }
        if !captureMethod.isEmpty {
            value["capture_method"] = captureMethod
        }
        if !appBundlePath.isEmpty {
            value["app_bundle_path"] = appBundlePath
        }
        if !appExecutablePath.isEmpty {
            value["app_executable_path"] = appExecutablePath
        }
        if !bundleIdentifier.isEmpty {
            value["bundle_identifier"] = bundleIdentifier
        }
        if !targetAppName.isEmpty {
            value["target_app_name"] = targetAppName
            value["window_owner"] = targetAppName
        }
        if !windowTitle.isEmpty {
            value["window_title"] = windowTitle
        }
        return value
    }
}

public enum JarvisClientError: Error, CustomStringConvertible {
    case invalidURL(String)
    case nonLoopbackURL(String)
    case missingResponse
    case streamMissingFinal
    case httpStatus(Int, String)

    public var description: String {
        switch self {
        case .invalidURL(let value):
            return "Invalid URL: \(value)"
        case .nonLoopbackURL(let value):
            return "Jarvis client only talks to loopback workers: \(value)"
        case .missingResponse:
            return "Missing HTTP response."
        case .streamMissingFinal:
            return "Streaming response ended without a final result."
        case .httpStatus(let status, let body):
            return "HTTP \(status): \(body)"
        }
    }
}
