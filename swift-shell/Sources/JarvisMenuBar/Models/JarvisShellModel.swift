import AppKit
import Foundation
import JarvisClient

@MainActor
final class JarvisShellModel: ObservableObject {
    @Published var command: String = ""
    @Published private(set) var connection: String = "Checking"
    @Published private(set) var state: String = "Idle"
    @Published private(set) var turnPhaseText: String = "Ready"
    @Published private(set) var tool: String = "No tool"
    @Published private(set) var resultText: String = "{}"
    @Published private(set) var confirmation: Confirmation?
    @Published private(set) var auditText: String = "Audit not loaded"
    @Published private(set) var codexText: String = "Codex not checked"
    @Published private(set) var codexActivity: CodexActivityResponse?
    @Published private(set) var codexActivityText: String = "No Codex activity yet"
    @Published private(set) var workerText: String = "Worker not checked"
    @Published private(set) var verificationText: String = "Verification not checked"
    @Published private(set) var modeText: String = "Mode not checked"
    @Published private(set) var isPaused: Bool = false
    @Published private(set) var permissionText: String = "Permissions not checked"
    @Published private(set) var permissions: [PermissionReadiness] = []
    @Published private(set) var isBusy: Bool = false
    @Published private(set) var wakeModeText: String = "Wake Off"
    @Published private(set) var wakeDetailText: String = "Hey Jarvis listener is off."
    @Published private(set) var wakeTranscriptText: String = ""
    @Published private(set) var isWakeListening: Bool = false
    @Published private(set) var isSpeechMuted: Bool = false
    @Published private(set) var speechMuteText: String = "Speech On"
    @Published private(set) var chatExportText: String = "Chat JSON ready"
    @Published private(set) var messages: [ChatMessage] = [
        ChatMessage(
            role: .jarvis,
            text: "I am online as the first local Jarvis prototype. Type a command, ask for status, or tell me to check your email."
        )
    ]

    private let client: JarvisClient
    private let workerSupervisor: JarvisWorkerSupervisor
    private let wakeListener = JarvisWakeListener()
    private var lastHealthDiagnostics: [String: Any] = [:]
    private var lastReadinessDiagnostics: [String: Any] = [:]
    private var lastCommandDiagnostics: [String: Any] = [:]
    private var monitoredCodexJobs: Set<String> = []
    private var codexActivityTask: Task<Void, Never>?
    private var activeTimerTasks: [String: Task<Void, Never>] = [:]
    private static let smokeTestPrompts = [
        "hello Jarvis",
        "tell me a short joke",
        "Give me a one-step algebra problem.",
        "x = 3",
        "Write five short bullets about making Jarvis feel fast.",
        "latency status",
        "model status",
        "elevation status",
        "memory status",
        "remote worker status",
        "capabilities status",
        "voice status",
        "tts status",
        "test status",
        "safety status",
        "what time is it",
        "what date is it",
        "battery status",
        "storage status",
        "set a timer for 5 seconds",
        "timer status",
        "cancel timers",
        "volume up",
        "sound down",
        "play current",
        "play current song",
        "play next",
        "play previous",
        "brightness up",
        "say exactly: Jarvis local exact route OK",
        "Hey Jarvis, check the time",
        "Hey Jarvis run sudo whoami",
        "ask Codex to say exactly: Jarvis Codex smoke test OK",
        "ask Codex to review this project",
        "codex jobs",
        "codex speed status",
        "permissions status",
        "screen status",
        "hotkey status",
        "wake status",
        "Hey Jarvis wake audition status",
        "Jarvis launch status",
        "email backend status",
        "check my email and summarize the newest email in my inbox",
        "check my second email",
        "read the visible Outlook screen with OCR",
        "what Mac is this",
        "stop talking",
        "Then click Copy Chat JSON and paste it back to Codex if anything looks wrong.",
    ]

    var dashboardURL: URL {
        client.baseURL
    }

    var wakeAuditionURL: URL {
        client.baseURL.appendingPathComponent("wake-audition/")
    }

    var appVersionText: String {
        let bundleVersion = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "unknown"
        return "Jarvis \(bundleVersion)"
    }

    init(client: JarvisClient? = nil) {
        let resolvedClient = client ?? (try? JarvisClient.fromEnvironment()) ?? JarvisClient(baseURL: URL(string: "http://127.0.0.1:8765")!)
        self.client = resolvedClient
        self.workerSupervisor = JarvisWorkerSupervisor(client: resolvedClient)
        configureWakeListener()
    }

    func refresh() {
        Task {
            await refreshNow()
        }
    }

    func refreshCodexActivityNow() {
        Task {
            codexActivityText = "Refreshing Codex activity..."
            await refreshCodexActivity()
        }
    }

    func startWorkerMonitoring() {
        workerSupervisor.startMonitoring { [weak self] status in
            guard let self else {
                return
            }
            workerText = status.description
            if status.isReady {
                connection = "Online"
                if case .started = status, !isBusy {
                    state = "Worker restarted"
                    Task {
                        await self.refreshNow()
                    }
                }
            } else {
                connection = "Offline"
                if !isBusy {
                    state = "Worker unavailable"
                }
            }
        }
    }

    func stopWorkerMonitoring() {
        wakeListener.stop()
        codexActivityTask?.cancel()
        codexActivityTask = nil
        workerSupervisor.stopMonitoring()
        workerSupervisor.stopStartedWorker()
    }

    func toggleWakeListener() {
        if isWakeListening {
            wakeListener.stop()
        } else {
            wakeListener.start()
        }
    }

    func stopWakeListener() {
        wakeListener.stop()
    }

    func toggleSpeechMuted() {
        let target = !isSpeechMuted
        applySpeechMuteState(muted: target)
        Task {
            do {
                let startup = await workerSupervisor.ensureRunning()
                workerText = startup.description
                guard startup.isReady else {
                    throw ShellModelError.workerUnavailable(startup.description)
                }
                let response = try await client.setSpeechMuted(target)
                applySpeechMuteResponse(response)
                state = response.muted ? "Muted" : "Ready"
                chatExportText = response.muted ? "Speech muted" : "Speech unmuted"
                messages.append(
                    ChatMessage(
                        role: .system,
                        text: response.muted ? "Jarvis speech is muted." : "Jarvis speech is on."
                    )
                )
            } catch {
                applySpeechMuteState(muted: !target)
                state = "Error"
                chatExportText = "Mute failed"
                messages.append(ChatMessage(role: .jarvis, text: "I could not change speech mute: \(error)"))
            }
        }
    }

    private func refreshSpeechMuteStatus() async {
        do {
            applySpeechMuteResponse(try await client.speechMuteStatus())
        } catch {
            speechMuteText = Self.speechMuteText(muted: isSpeechMuted)
        }
    }

    private func applySpeechMuteResponse(_ response: SpeechMuteResponse) {
        applySpeechMuteState(muted: response.muted)
    }

    private func applySpeechMuteState(muted: Bool) {
        isSpeechMuted = muted
        speechMuteText = Self.speechMuteText(muted: muted)
    }

    static func speechMuteText(muted: Bool) -> String {
        muted ? "Muted" : "Speech On"
    }

    private func configureWakeListener() {
        wakeListener.onStateChange = { [weak self] snapshot in
            guard let self else {
                return
            }
            isWakeListening = snapshot.running
            wakeModeText = "Wake \(snapshot.phase)"
            wakeDetailText = "\(snapshot.status) via \(snapshot.engine)"
            wakeTranscriptText = snapshot.transcript
        }
        wakeListener.onWakeDetected = { [weak self] transcript in
            guard let self else {
                return
            }
            state = "Listening"
            turnPhaseText = "Awake"
            wakeTranscriptText = transcript
            messages.append(ChatMessage(role: .jarvis, text: "Yes sir?", detail: "Wake detected."))
            Task {
                if !self.isSpeechMuted {
                    _ = try? await self.client.speakStatus("Yes sir?")
                }
            }
        }
        wakeListener.onCommandCaptured = { [weak self] command, transcript in
            guard let self else {
                return
            }
            wakeTranscriptText = transcript
            wakeDetailText = "Captured: \(command)"
            guard !isBusy else {
                messages.append(ChatMessage(role: .jarvis, text: "I heard \(command), but I am still finishing the current task.", detail: "Wake command held."))
                return
            }
            submit(command)
        }
    }

    func submitCurrentCommand() {
        submit(command)
    }

    func pasteFromClipboard() {
        guard let text = NSPasteboard.general.string(forType: .string), !text.isEmpty else {
            chatExportText = "Clipboard empty"
            return
        }
        command = text.trimmingCharacters(in: .whitespacesAndNewlines)
        chatExportText = "Pasted"
    }

    func submit(_ commandText: String) {
        let trimmed = commandText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else {
            return
        }
        messages.append(ChatMessage(role: .user, text: trimmed))
        command = ""

        Task {
            await runCommand(trimmed)
        }
    }

    func copyChatHistoryJSON() {
        let bundleVersion = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "unknown"
        let bundleBuild = Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String ?? "unknown"
        let payload: [String: Any] = [
            "schema": "jarvis.chat.debug.v1",
            "exported_at": ISO8601DateFormatter().string(from: Date()),
            "app": [
                "name": "Jarvis",
                "version": bundleVersion,
                "build": bundleBuild,
                "base_url": dashboardURL.absoluteString,
                "connection": connection,
                "state": state,
                "turn_phase": turnPhaseText,
                "tool": tool,
                "mode": modeText,
                "worker": workerText,
                "codex": codexText,
                "codex_activity": codexActivityText,
                "verification": verificationText,
                "permission_summary": permissionText,
            "wake": [
                "mode": wakeModeText,
                "detail": wakeDetailText,
                "transcript": Self.redactChatExportText(wakeTranscriptText),
                "listening": isWakeListening,
            ],
            "speech": [
                "muted": isSpeechMuted,
                "mute_label": speechMuteText,
            ],
            "fast_model": Self.redactedJSONValue(lastHealthDiagnostics["fast_model"] ?? NSNull()),
            "worker_runtime": Self.redactedJSONValue(lastHealthDiagnostics["runtime"] ?? NSNull()),
            ],
            "diagnostics": [
                "health": Self.redactedJSONValue(lastHealthDiagnostics),
                "readiness": Self.redactedJSONValue(lastReadinessDiagnostics),
                "permissions": Self.redactedJSONValue(Self.permissionDiagnostics(permissions)),
                "codex_activity": Self.redactedJSONValue(Self.codexActivityDiagnostics(codexActivity)),
                "last_response": Self.redactedJSONValue(lastCommandDiagnostics),
            ],
            "current_command": Self.redactChatExportText(command),
            "last_result_text": Self.redactChatExportText(resultText),
            "messages": messages.map { message in
                var item: [String: Any] = [
                    "id": message.id.uuidString,
                    "role": message.role.rawValue,
                    "text": Self.redactChatExportText(message.text),
                ]
                if let detail = message.detail, !detail.isEmpty {
                    item["detail"] = Self.redactChatExportText(detail)
                }
                return item
            },
        ]

        do {
            let data = try JSONSerialization.data(withJSONObject: payload, options: [.prettyPrinted, .sortedKeys])
            guard let text = String(data: data, encoding: .utf8) else {
                throw ShellModelError.exportFailed("Could not encode chat JSON as UTF-8.")
            }
            let pasteboard = NSPasteboard.general
            pasteboard.clearContents()
            pasteboard.setString(text, forType: .string)
            chatExportText = "Copied \(messages.count) messages"
            state = "Copied"
        } catch {
            chatExportText = "Copy failed"
            messages.append(ChatMessage(role: .jarvis, text: "I could not copy the chat JSON: \(error)"))
        }
    }

    func copySmokeTestPrompts() {
        let text = Self.smokeTestPrompts.enumerated()
            .map { index, prompt in "\(index + 1). \(prompt)" }
            .joined(separator: "\n")
        let pasteboard = NSPasteboard.general
        pasteboard.clearContents()
        pasteboard.setString(text, forType: .string)
        chatExportText = "Copied \(Self.smokeTestPrompts.count) tests"
        state = "Copied"
    }

    private func refreshNow() async {
        await refreshPermissionReadiness()
        let startup = await workerSupervisor.ensureRunning()
        workerText = startup.description
        guard startup.isReady else {
            connection = "Offline"
            auditText = "Audit unavailable"
            codexText = "Worker unavailable"
            codexActivityText = "Worker unavailable"
            return
        }

        do {
            let health = try await client.health()
            connection = health.ok ? "Online" : "Issue"
            codexText = health.status.codex.version ?? "Codex CLI not found"
            lastHealthDiagnostics = Self.healthDiagnostics(from: health)
            let runningCodexJobCount = health.status.codexJobs?.runningCount ?? 0
            await refreshSpeechMuteStatus()
            await refreshCodexActivity()
            if runningCodexJobCount > 0 {
                startCodexActivityPolling()
            }
            if let mode = health.mode {
                applyMode(mode)
            } else {
                await refreshMode()
            }
            if let runtime = health.status.runtime {
                workerText = "\(startup.description) | pid \(runtime.pid), uptime \(Self.formatUptime(runtime.uptimeSeconds))"
            }

            let audit = try await client.auditStatus()
            auditText = "\(audit.eventCount) events, \(audit.byteSizeHuman), \(audit.retentionDays)d retention, cap \(audit.maxBytesHuman)"
            let readiness = try await client.readiness()
            verificationText = Self.formatVerification(readiness.verification)
            lastReadinessDiagnostics = Self.readinessDiagnostics(from: readiness)
        } catch {
            connection = "Offline"
            auditText = "Audit unavailable"
            codexText = "Worker unavailable"
            codexActivityText = "Codex activity unavailable"
            verificationText = "Verification unavailable"
        }
    }

    func togglePause() {
        Task {
            isBusy = true
            state = isPaused ? "Resuming" : "Pausing"
            do {
                let startup = await workerSupervisor.ensureRunning()
                workerText = startup.description
                guard startup.isReady else {
                    throw ShellModelError.workerUnavailable(startup.description)
                }
                let mode = try await client.setPaused(!isPaused, reason: "Swift shell toggle.")
                applyMode(mode)
                state = mode.paused ? "Paused" : "Ready"
                messages.append(ChatMessage(role: .system, text: mode.paused ? "Jarvis command execution is paused." : "Jarvis command execution is live."))
                await refreshNow()
            } catch {
                state = "Error"
                resultText = "Jarvis mode error:\n\(error)"
                messages.append(ChatMessage(role: .jarvis, text: "I could not change pause mode: \(error)"))
            }
            isBusy = false
        }
    }

    private func refreshPermissionReadiness() async {
        let snapshot = await JarvisPermissionService.snapshot()
        permissions = snapshot
        permissionText = JarvisPermissionService.summary(snapshot)
    }

    private func refreshMode() async {
        do {
            applyMode(try await client.mode())
        } catch {
            modeText = "Mode unavailable"
            isPaused = false
        }
    }

    private func applyMode(_ mode: ModeResponse) {
        isPaused = mode.paused
        modeText = mode.paused ? "Paused" : "Live"
        if mode.paused {
            state = "Paused"
        }
    }

    private func runCommand(_ commandText: String) async {
        isBusy = true
        state = "Thinking"
        turnPhaseText = "Thinking"
        confirmation = nil
        tool = "No tool"
        let turnStartedAt = Date()
        var turnEvents: [[String: Any]] = []
        var visibleStatusLines: [String] = []
        var finalVisibleText = ""
        var finalSpeechDiagnostics: Any = NSNull()
        var routeSource: String?
        var modelBackend: String?
        var modelName: String?
        var turnEndedCleanly = false

        func recordTurnPhase(_ phase: String, detail: String? = nil) {
            turnPhaseText = phase
            turnEvents.append(Self.turnEvent(phase, startedAt: turnStartedAt, detail: detail))
        }

        func captureResponseDiagnostics(_ response: CommandResponse) {
            finalSpeechDiagnostics = response.speech?.anyValue ?? NSNull()
            routeSource = Self.routeSource(from: response)
            modelBackend = Self.modelBackend(from: response)
            modelName = Self.modelName(from: response)
        }

        recordTurnPhase("Heard", detail: "User command accepted.")
        recordTurnPhase("Thinking", detail: "Choosing direct answer or tool route.")
        let history = conversationHistoryPayload(currentCommand: commandText)
        var placeholderId: UUID?
        var progressTask: Task<Void, Never>?
        defer {
            progressTask?.cancel()
            if state == "Error" {
                recordTurnPhase("Error", detail: "Turn ended with a worker or app error.")
            } else if !turnEndedCleanly {
                recordTurnPhase("Done", detail: "Turn lifecycle finished.")
            }
            var diagnostics = lastCommandDiagnostics
            diagnostics["turn_trace"] = Self.turnTrace(
                command: commandText,
                startedAt: turnStartedAt,
                events: turnEvents,
                visibleStatusLines: visibleStatusLines,
                finalVisibleText: finalVisibleText,
                finalSpeech: finalSpeechDiagnostics,
                routeSource: routeSource,
                modelBackend: modelBackend,
                modelName: modelName,
                state: state,
                tool: tool
            )
            lastCommandDiagnostics = diagnostics
            isBusy = false
        }

        do {
            if Self.shouldUseNativeHotKeyStatus(commandText) {
                recordTurnPhase("Working", detail: "Using native keyboard shortcut status.")
                let placeholderId = appendJarvisMessage(text: "Checking keyboard shortcut status.", detail: "Working")
                visibleStatusLines.append("Checking keyboard shortcut status.")
                runNativeHotKeyStatus(commandText, placeholderId: placeholderId)
                finalVisibleText = messages.first(where: { $0.id == placeholderId })?.text ?? ""
                turnEndedCleanly = true
                recordTurnPhase("Done", detail: "Native keyboard shortcut status displayed.")
                return
            }

            if Self.shouldUseNativeVoiceStatus(commandText) {
                recordTurnPhase("Working", detail: "Using native voice status.")
                let placeholderId = appendJarvisMessage(text: "Checking voice status.", detail: "Working")
                visibleStatusLines.append("Checking voice status.")
                await runNativeVoiceStatus(commandText, placeholderId: placeholderId)
                finalVisibleText = messages.first(where: { $0.id == placeholderId })?.text ?? ""
                turnEndedCleanly = true
                recordTurnPhase("Done", detail: "Native voice status displayed.")
                return
            }

            if Self.shouldUseNativeTestStatus(commandText) {
                recordTurnPhase("Working", detail: "Using native smoke-test status.")
                let placeholderId = appendJarvisMessage(text: "Checking test prompts.", detail: "Working")
                visibleStatusLines.append("Checking test prompts.")
                runNativeTestStatus(commandText, placeholderId: placeholderId)
                finalVisibleText = messages.first(where: { $0.id == placeholderId })?.text ?? ""
                turnEndedCleanly = true
                recordTurnPhase("Done", detail: "Native smoke-test status displayed.")
                return
            }

            if Self.shouldUseNativePermissionStatus(commandText) {
                recordTurnPhase("Working", detail: "Using native permission status.")
                let placeholderId = appendJarvisMessage(text: "Checking permissions.", detail: "Working")
                visibleStatusLines.append("Checking permissions.")
                await runNativePermissionStatus(commandText, placeholderId: placeholderId)
                finalVisibleText = messages.first(where: { $0.id == placeholderId })?.text ?? ""
                turnEndedCleanly = true
                recordTurnPhase("Done", detail: "Native permission status displayed.")
                return
            }

            if Self.shouldUseNativeScreenStatus(commandText) {
                recordTurnPhase("Working", detail: "Using native screen status.")
                let placeholderId = appendJarvisMessage(text: "Checking screen status.", detail: "Working")
                visibleStatusLines.append("Checking screen status.")
                await runNativeScreenStatus(commandText, placeholderId: placeholderId)
                finalVisibleText = messages.first(where: { $0.id == placeholderId })?.text ?? ""
                turnEndedCleanly = true
                recordTurnPhase("Done", detail: "Native screen status displayed.")
                return
            }

            let startup = await workerSupervisor.ensureRunning()
            workerText = startup.description
            guard startup.isReady else {
                throw ShellModelError.workerUnavailable(startup.description)
            }
            recordTurnPhase("Working", detail: "Worker is ready.")
            let response: CommandResponse
            if Self.shouldUseNativeOutlookRead(commandText) {
                let statusText = "Yes sir, checking what Outlook is showing now."
                _ = appendJarvisMessage(text: statusText, detail: "Working")
                visibleStatusLines.append(statusText)
                if !isSpeechMuted {
                    _ = try? await client.speakStatus(statusText)
                }
                recordTurnPhase("Working", detail: statusText)
                response = try await runNativeOutlookRead(commandText)
            } else {
                var streamedReply = ""
                var lastStatusText = ""
                response = try await client.sendStreaming(
                    command: commandText,
                    history: history,
                    onStatus: { status in
                        let statusText = status.trimmingCharacters(in: .whitespacesAndNewlines)
                        guard !statusText.isEmpty, statusText != lastStatusText else {
                            return
                        }
                        lastStatusText = statusText
                        visibleStatusLines.append(statusText)
                        recordTurnPhase("Working", detail: statusText)
                        if !streamedReply.isEmpty {
                            if progressTask == nil {
                                progressTask = self.startProgressNudges(for: commandText)
                            }
                            return
                        }
                        if let placeholderId {
                            self.replaceMessage(
                                id: placeholderId,
                                with: ChatMessage(
                                    id: placeholderId,
                                    role: .jarvis,
                                    text: statusText,
                                    detail: "Working"
                                )
                            )
                        } else {
                            _ = self.appendJarvisMessage(text: statusText, detail: "Working")
                        }
                        if progressTask == nil {
                            progressTask = self.startProgressNudges(for: commandText)
                        }
                    },
                    onDelta: { delta in
                        progressTask?.cancel()
                        if streamedReply.isEmpty {
                            recordTurnPhase("Answering", detail: "First visible answer text arrived.")
                        }
                        streamedReply += delta
                        let id = placeholderId ?? self.appendJarvisMessage(text: streamedReply, detail: "Streaming")
                        placeholderId = id
                        self.replaceMessage(
                            id: id,
                            with: ChatMessage(
                                id: id,
                                role: .jarvis,
                                text: streamedReply,
                                detail: "Streaming"
                            )
                        )
                    }
                )
            }
            tool = response.tool ?? "unknown"
            confirmation = response.confirmation
            state = response.confirmation?.required == true ? "Approval" : "Ready"
            resultText = render(response)
            lastCommandDiagnostics = Self.commandDiagnostics(from: response)
            captureResponseDiagnostics(response)
            let finalText = assistantReply(for: response)
            finalVisibleText = finalText
            let finalDetail = chatDetail(for: response)
            recordTurnPhase("Answering", detail: "Final visible answer displayed.")
            if let placeholderId {
                replaceMessage(
                    id: placeholderId,
                    with:
                    ChatMessage(
                        id: placeholderId,
                        role: .jarvis,
                        text: finalText,
                        detail: finalDetail
                    )
                )
            } else {
                messages.append(ChatMessage(role: .jarvis, text: finalText, detail: finalDetail))
            }
            startCodexJobMonitorIfNeeded(from: response)
            updateTimerMirrorsIfNeeded(from: response)
            turnEndedCleanly = true
            turnPhaseText = response.confirmation?.required == true ? "Approval" : "Done"
            recordTurnPhase(turnPhaseText, detail: "Turn lifecycle finished.")
            await refreshNow()
        } catch {
            state = "Error"
            turnPhaseText = "Error"
            tool = "No tool"
            resultText = "Jarvis worker error:\n\(error)"
            lastCommandDiagnostics = [
                "status": "error",
                "command": commandText,
                "error": "\(error)",
            ]
            if let placeholderId {
                replaceMessage(
                    id: placeholderId,
                    with: ChatMessage(id: placeholderId, role: .jarvis, text: "I hit a worker error: \(error)")
                )
                finalVisibleText = "I hit a worker error: \(error)"
            } else {
                messages.append(ChatMessage(role: .jarvis, text: "I hit a worker error: \(error)"))
                finalVisibleText = "I hit a worker error: \(error)"
            }
        }
    }

    private func runNativeHotKeyStatus(_ commandText: String, placeholderId: UUID) {
        state = "Ready"
        tool = "hotkey.native_status"
        let shortcut = JarvisHotKeyService.defaultShortcut.displayName
        let reply = [
            "Keyboard shortcut: \(shortcut).",
            "Press it to open or focus the Jarvis panel.",
            "Experimental Hey Jarvis microphone wake is available from the app panel.",
        ].joined(separator: "\n")
        resultText = [
            "Command: \(commandText)",
            "Tool: hotkey.native_status",
            "Executed: true",
            "Summary: Read native hotkey status.",
            "Shortcut: \(shortcut)",
        ].joined(separator: "\n")
        lastCommandDiagnostics = [
            "command": commandText,
            "tool": "hotkey.native_status",
            "summary": "Read native hotkey status.",
            "executed": true,
            "shortcut": shortcut,
            "voice_wake_active": false,
        ]
        replaceMessage(
            id: placeholderId,
            with: ChatMessage(
                id: placeholderId,
                role: .jarvis,
                text: reply,
                detail: "Read native hotkey status."
            )
        )
    }

    private func runNativePermissionStatus(_ commandText: String, placeholderId: UUID) async {
        state = "Checking Permissions"
        tool = "permissions.native_status"
        let snapshot = await JarvisPermissionService.snapshot()
        permissions = snapshot
        permissionText = JarvisPermissionService.summary(snapshot)
        let reply = Self.permissionStatusReply(snapshot)
        let target = Self.permissionTargetDiagnostics()
        resultText = [
            "Command: \(commandText)",
            "Tool: permissions.native_status",
            "Executed: true",
            "Summary: Read native permission status.",
            "Permission target: \(target["path"] ?? "unknown")",
            "Bundle ID: \(target["bundle_id"] ?? "unknown")",
            permissionText,
        ].joined(separator: "\n")
        lastCommandDiagnostics = [
            "command": commandText,
            "tool": "permissions.native_status",
            "summary": "Read native permission status.",
            "executed": true,
            "permission_target": target,
            "permissions": Self.permissionDiagnostics(snapshot),
        ]
        replaceMessage(
            id: placeholderId,
            with: ChatMessage(
                id: placeholderId,
                role: .jarvis,
                text: reply,
                detail: "Read native permission status."
            )
        )
        state = "Ready"
    }

    private func runNativeScreenStatus(_ commandText: String, placeholderId: UUID) async {
        state = "Checking Screen"
        tool = "screen.native_status"
        let snapshot = await JarvisPermissionService.snapshot()
        permissions = snapshot
        permissionText = JarvisPermissionService.summary(snapshot)
        let screen = snapshot.first(where: { $0.id == "screen-recording" })
        let target = Self.permissionTargetDiagnostics()
        let ready = screen?.isReady == true
        let reply = [
            "Screen status:",
            "- Screen Recording: \(screen?.state ?? "Unknown"). \(screen?.detail ?? "No Screen Recording status available.")",
            "- Native visible OCR: \(ready ? "available when Outlook is visible" : "blocked until Screen Recording is granted to this app").",
            "- Permission target: \(target["path"] ?? "unknown")",
            "- Bundle ID: \(target["bundle_id"] ?? "unknown")",
            "This did not capture the screen, run OCR, or store an image.",
        ].joined(separator: "\n")
        resultText = [
            "Command: \(commandText)",
            "Tool: screen.native_status",
            "Executed: true",
            "Summary: Read native screen status.",
            "Screen Recording: \(screen?.state ?? "Unknown")",
            "Native OCR available: \(ready)",
            "Permission target: \(target["path"] ?? "unknown")",
            "Captured screen: false",
        ].joined(separator: "\n")
        lastCommandDiagnostics = [
            "command": commandText,
            "tool": "screen.native_status",
            "summary": "Read native screen status.",
            "executed": true,
            "permission_target": target,
            "screen_recording": screen?.state ?? "Unknown",
            "native_ocr_available": ready,
            "captured_screen": false,
            "stored_screenshot": false,
        ]
        replaceMessage(
            id: placeholderId,
            with: ChatMessage(
                id: placeholderId,
                role: .jarvis,
                text: reply,
                detail: "Read native screen status."
            )
        )
        state = "Ready"
    }

    private func runNativeVoiceStatus(_ commandText: String, placeholderId: UUID) async {
        state = "Checking Voice"
        tool = "voice.native_status"
        let snapshot = await JarvisPermissionService.snapshot()
        permissions = snapshot
        permissionText = JarvisPermissionService.summary(snapshot)
        let microphone = snapshot.first(where: { $0.id == "microphone" })
        let speech = snapshot.first(where: { $0.id == "speech-recognition" })
        let shortcut = JarvisHotKeyService.defaultShortcut.displayName
        let reply = [
            "Voice status:",
            "- Microphone: \(microphone?.state ?? "Unknown"). \(microphone?.detail ?? "No microphone status available.")",
            "- Speech Recognition: \(speech?.state ?? "Unknown"). \(speech?.detail ?? "No speech-recognition status available.")",
            "- Keyboard wake/focus: \(shortcut).",
            "- Typed wake simulation: available for Hey Jarvis, OK Jarvis, and Okay Jarvis.",
            "- Experimental Hey Jarvis microphone listener: \(isWakeListening ? "running" : "available but off").",
            "- Speech-to-text command transcription: available through the experimental listener; dictated text is treated as punctuation-poor input.",
            "- TTS: \(isSpeechMuted ? "muted from the app menu" : "automatic final spoken replies are enabled for supported routes, and explicit local `speak ...` / `say out loud ...` commands still exist").",
            "This did not record audio, transcribe audio, or request new permissions.",
        ].joined(separator: "\n")
        resultText = [
            "Command: \(commandText)",
            "Tool: voice.native_status",
            "Executed: true",
            "Summary: Read native voice status.",
            "Microphone: \(microphone?.state ?? "Unknown")",
            "Speech Recognition: \(speech?.state ?? "Unknown")",
            "Voice wake active: \(isWakeListening)",
        ].joined(separator: "\n")
        lastCommandDiagnostics = [
            "command": commandText,
            "tool": "voice.native_status",
            "summary": "Read native voice status.",
            "executed": true,
            "permissions": Self.permissionDiagnostics(snapshot),
            "keyboard_shortcut": shortcut,
            "typed_wake_simulation_available": true,
            "microphone_wake_available": true,
            "speech_to_text_available": true,
            "experimental_wake_listener_available": true,
            "experimental_wake_listener_active": isWakeListening,
            "wake_transcript": Self.redactChatExportText(wakeTranscriptText),
            "speech_muted": isSpeechMuted,
            "automatic_tts_enabled": true,
            "final_answer_speech_expected": true,
        ]
        replaceMessage(
            id: placeholderId,
            with: ChatMessage(
                id: placeholderId,
                role: .jarvis,
                text: reply,
                detail: "Read native voice status."
            )
        )
        state = "Ready"
    }

    private func runNativeTestStatus(_ commandText: String, placeholderId: UUID) {
        state = "Ready"
        tool = "tests.native_status"
        let count = Self.smokeTestPrompts.count
        let preview = Self.smokeTestPrompts.prefix(6).joined(separator: ", ")
        let reply = [
            "Test status: Copy Tests currently has \(count) prompts.",
            "Click Copy Tests to put the full smoke-test set on the clipboard.",
            "First prompts: \(preview).",
            "Private tests are still the email and visible-OCR prompts; paste Copy Chat JSON back to Codex if anything looks wrong.",
        ].joined(separator: "\n")
        resultText = [
            "Command: \(commandText)",
            "Tool: tests.native_status",
            "Executed: true",
            "Summary: Read native test status.",
            "Copy Tests count: \(count)",
        ].joined(separator: "\n")
        lastCommandDiagnostics = [
            "command": commandText,
            "tool": "tests.native_status",
            "summary": "Read native test status.",
            "executed": true,
            "smoke_test_count": count,
            "smoke_test_prompts": Self.smokeTestPrompts,
        ]
        replaceMessage(
            id: placeholderId,
            with: ChatMessage(
                id: placeholderId,
                role: .jarvis,
                text: reply,
                detail: "Read native test status."
            )
        )
    }

    private func updateTimerMirrorsIfNeeded(from response: CommandResponse) {
        guard response.tool == "quick.local_control",
              let object = response.result?.objectValue else {
            return
        }

        let action = object["action"]?.stringValue ?? ""
        if action == "timer.cancel" {
            for task in activeTimerTasks.values {
                task.cancel()
            }
            activeTimerTasks.removeAll()
            return
        }

        guard action == "timer",
              object["status"]?.stringValue == "timer_started",
              let timerId = object["timer_id"]?.stringValue,
              let durationSeconds = object["duration_seconds"]?.intValue,
              durationSeconds > 0 else {
            return
        }

        activeTimerTasks[timerId]?.cancel()
        activeTimerTasks[timerId] = Task { [weak self] in
            do {
                try await Task.sleep(nanoseconds: UInt64(durationSeconds) * 1_000_000_000)
            } catch {
                return
            }
            self?.completeTimerMirror(timerId: timerId, durationSeconds: durationSeconds)
        }
    }

    private func completeTimerMirror(timerId: String, durationSeconds: Int) {
        activeTimerTasks.removeValue(forKey: timerId)
        messages.append(
            ChatMessage(
                role: .jarvis,
                text: "Timer finished: \(Self.formatDuration(durationSeconds)).",
                detail: "Local timer"
            )
        )
        chatExportText = "Timer finished"
    }

    private func startCodexJobMonitorIfNeeded(from response: CommandResponse) {
        guard response.tool == "codex.job",
              let object = response.result?.objectValue,
              object["status"]?.stringValue == "running",
              let jobId = object["job_id"]?.stringValue,
              !jobId.isEmpty,
              !monitoredCodexJobs.contains(jobId) else {
            return
        }

        monitoredCodexJobs.insert(jobId)
        startCodexActivityPolling()
        Task {
            await monitorCodexJob(jobId)
        }
    }

    private func startCodexActivityPolling() {
        codexActivityTask?.cancel()
        codexActivityTask = Task { [weak self] in
            var idlePolls = 0
            while !Task.isCancelled {
                guard let self else {
                    return
                }
                await self.refreshCodexActivity()
                if (self.codexActivity?.runningCount ?? 0) > 0 {
                    idlePolls = 0
                } else {
                    idlePolls += 1
                    if idlePolls >= 2 {
                        break
                    }
                }
                do {
                    try await Task.sleep(nanoseconds: 2_000_000_000)
                } catch {
                    return
                }
            }
        }
    }

    private func refreshCodexActivity() async {
        do {
            let activity = try await client.codexActivity()
            codexActivity = activity
            codexActivityText = Self.formatCodexActivity(activity)
        } catch {
            codexActivityText = "Codex activity unavailable"
        }
    }

    private func monitorCodexJob(_ jobId: String) async {
        defer {
            monitoredCodexJobs.remove(jobId)
        }

        for attempt in 1...72 {
            do {
                try await Task.sleep(nanoseconds: 5_000_000_000)
            } catch {
                return
            }

            do {
                await refreshCodexActivity()
                let response = try await client.send(command: "codex job \(jobId)")
                let status = response.result?.objectValue?["status"]?.stringValue ?? "unknown"
                if status == "running" {
                    if attempt % 6 == 0 {
                        chatExportText = "Codex job running"
                    }
                    continue
                }

                tool = response.tool ?? "codex.job"
                resultText = render(response)
                lastCommandDiagnostics = Self.commandDiagnostics(from: response)
                messages.append(
                    ChatMessage(
                        role: .jarvis,
                        text: "Codex job \(jobId) finished:\n\(assistantReply(for: response))",
                        detail: chatDetail(for: response)
                    )
                )
                chatExportText = "Codex job finished"
                await refreshCodexActivity()
                await refreshNow()
                return
            } catch {
                if attempt % 6 == 0 {
                    chatExportText = "Codex job check failed"
                }
            }
        }

        messages.append(
            ChatMessage(
                role: .jarvis,
                text: "Codex job \(jobId) is still running after 6 minutes. Ask `codex job \(jobId)` for the latest status.",
                detail: "Codex job monitor stopped"
            )
        )
    }

    private func appendJarvisMessage(text: String, detail: String? = nil) -> UUID {
        let message = ChatMessage(role: .jarvis, text: text, detail: detail)
        messages.append(message)
        return message.id
    }

    private func conversationHistoryPayload(currentCommand: String) -> [[String: String]] {
        Self.conversationHistoryPayload(from: messages, currentCommand: currentCommand)
    }

    static func conversationHistoryPayload(from messages: [ChatMessage], currentCommand: String) -> [[String: String]] {
        let current = currentCommand.trimmingCharacters(in: .whitespacesAndNewlines)
        let eligible: [[String: String]] = messages.compactMap { message in
            let text = message.text.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !text.isEmpty else {
                return nil
            }
            if message.role == .user && text == current {
                return nil
            }
            if message.role == .jarvis, message.detail == "Working" {
                return nil
            }
            if message.role == .system {
                return nil
            }
            let role: String
            switch message.role {
            case .user:
                role = "user"
            case .jarvis:
                role = "assistant"
            case .system:
                role = "system"
            }
            return ["role": role, "text": String(text.prefix(900))]
        }
        return Array(eligible.suffix(12))
    }

    private func startProgressNudges(for commandText: String) -> Task<Void, Never> {
        let nudges = Self.progressReplies(for: commandText)
        return Task { [weak self] in
            for nudge in nudges {
                do {
                    try await Task.sleep(nanoseconds: nudge.delayNanoseconds)
                } catch {
                    return
                }
                await MainActor.run {
                    guard let self, self.isBusy else {
                        return
                    }
                    self.messages.append(
                        ChatMessage(
                            role: .jarvis,
                            text: nudge.text,
                            detail: "Working"
                        )
                    )
                }
            }
        }
    }

    private func replaceMessage(id: UUID, with replacement: ChatMessage) {
        guard let index = messages.firstIndex(where: { $0.id == id }) else {
            messages.append(replacement)
            return
        }
        messages[index] = replacement
    }

    private func runNativeOutlookRead(_ commandText: String) async throws -> CommandResponse {
        let mode = try await client.mode()
        applyMode(mode)
        guard !mode.paused else {
            return try await client.send(command: commandText)
        }

        state = "Reading Outlook"
        tool = "native.vision_ocr"
        do {
            let capture = try await JarvisNativeOutlookReader.readVisibleOutlookText()
            return try await client.summarizeVisibleOutlookText(
                command: commandText,
                text: capture.text,
                diagnostics: capture.diagnostics
            )
        } catch {
            return try await client.summarizeVisibleOutlookText(
                command: commandText,
                text: "",
                diagnostics: JarvisNativeOutlookReader.failureDiagnostics(for: error)
            )
        }
    }

    private func assistantReply(for response: CommandResponse) -> String {
        if let confirmation = response.confirmation, confirmation.required {
            var lines = [confirmation.title]
            if let message = confirmation.message {
                lines.append(message)
            }
            if let phrase = confirmation.exactPhrase {
                lines.append("To approve this later, type exactly: \(phrase)")
            }
            return lines.joined(separator: "\n")
        }

        if response.tool == "outlook.visible_summary" {
            if let object = response.result?.objectValue {
                if let emailSummary = object["email_summary"]?.stringValue?.trimmingCharacters(in: .whitespacesAndNewlines),
                   !emailSummary.isEmpty {
                    return emailSummary
                }
                if let reply = object["reply"]?.stringValue?.trimmingCharacters(in: .whitespacesAndNewlines),
                   !reply.isEmpty,
                   object["source"]?.stringValue?.contains("ocr") != true {
                    return reply
                }
            }
            return outlookReply(from: response.result)
        }

        if let reply = response.result?.objectValue?["reply"]?.stringValue {
            return reply
        }

        switch response.tool {
        case "system.status":
            return "I checked the local worker. Jarvis is online and the status details are available below."
        case "files.search":
            return "I searched the project files and updated the result details."
        case "screenshot.capability":
            return "I checked screen-capture capability. This prototype does not store screenshots by default."
        case "codex.delegate":
            return "I prepared a Codex delegation plan. I did not run Codex yet."
        case "browser.open_url":
            return "I prepared a browser action plan. I did not open a webpage yet."
        case "policy.pause":
            return "Jarvis is paused, so I did not run that command."
        default:
            return response.summary ?? "Done."
        }
    }

    private func chatDetail(for response: CommandResponse) -> String? {
        guard let object = response.result?.objectValue else {
            return response.summary
        }

        var parts: [String] = []
        if let backend = object["backend"]?.stringValue, !backend.isEmpty,
           let model = object["model"]?.stringValue, !model.isEmpty {
            parts.append("\(Self.backendLabel(backend)) \(model)")
        } else if let model = object["model"]?.stringValue, !model.isEmpty {
            parts.append(model)
        } else if let backend = object["email_summary_backend"]?.stringValue, !backend.isEmpty {
            if let model = object["email_summary_model"]?.stringValue, !model.isEmpty {
                parts.append("Email summary: \(Self.backendLabel(backend)) \(model)")
            } else {
                parts.append("Email summary: \(Self.backendLabel(backend))")
            }
        }

        let timing = object["duration_human"]?.stringValue
            ?? object["email_summary_duration_human"]?.stringValue
            ?? object["duration_seconds"]?.doubleValue.map { String(format: "%.1fs", $0) }
        if let timing, !timing.isEmpty {
            parts.append("\(Self.timingLabel(for: response.tool)): \(timing)")
        }

        let firstVisible = object["first_visible_token_seconds"]?.doubleValue
            ?? object["first_token_seconds"]?.doubleValue
        if let firstVisible {
            parts.append(String(format: "First visible: %.1fs", firstVisible))
        }

        if !parts.isEmpty {
            return parts.joined(separator: " | ")
        }
        return response.summary
    }

    private func outlookReply(from result: JSONValue?) -> String {
        guard let object = result?.objectValue else {
            return "I tried to check Outlook, but the worker did not return a readable email summary."
        }

        let status = object["status"]?.stringValue ?? "unknown"
        if status == "checked" {
            let rows = object["messages"]?.arrayValue?.compactMap(\.objectValue) ?? []
            if rows.isEmpty {
                return "I checked Outlook, but I could not read any inbox messages from the route this prototype can access."
            }

            let scanned = object["scanned_count"]?.intValue ?? rows.count
            let source = object["source"]?.stringValue ?? "unknown"
            if source.contains("ocr") {
                var lines = [object["reply"]?.stringValue ?? "I read the visible Outlook window locally with OCR."]
                for row in rows {
                    if let snippet = row["snippet"]?.stringValue, !snippet.isEmpty {
                        lines.append(snippet)
                    }
                }
                if let warning = Self.injectionWarning(from: object) {
                    lines.append(warning)
                }
                lines.append("This stayed local. I did not send the email or screenshot to a model.")
                return lines.joined(separator: "\n")
            }
            let mailbox = Self.mailboxLabel(for: source)
            let unreadCount = object["unread_count"]?.intValue ?? rows.filter {
                ($0["read_state"]?.stringValue ?? "").lowercased() == "unread"
            }.count
            let selectionMode = object["selection_mode"]?.stringValue ?? (unreadCount > 0 ? "unread" : "latest")
            var lines = [
                Self.mailSelectionIntro(
                    mailbox: mailbox,
                    scanned: scanned,
                    unreadCount: unreadCount,
                    selectedCount: rows.count,
                    selectionMode: selectionMode
                )
            ]
            if let emailSummary = object["email_summary"]?.stringValue?.trimmingCharacters(in: .whitespacesAndNewlines),
               !emailSummary.isEmpty {
                let fallbackUsed = object["email_summary_fallback_used"]?.boolValue == true
                let quality = object["email_summary_quality"]?.stringValue ?? ""
                if quality == "metadata_only" {
                    lines.append("Metadata summary:")
                } else if fallbackUsed {
                    lines.append("Fallback summary:")
                } else {
                    lines.append("Summary:")
                }
                lines.append(emailSummary)
                if let warning = Self.injectionWarning(from: object) {
                    lines.append(warning)
                }
                if object["email_summary_local_only"]?.boolValue == true {
                    if fallbackUsed,
                       let configuredBackend = object["email_summary_backend"]?.stringValue,
                       let effectiveBackend = object["email_summary_effective_backend"]?.stringValue,
                       !configuredBackend.isEmpty,
                       !effectiveBackend.isEmpty,
                       configuredBackend.lowercased() != effectiveBackend.lowercased() {
                        lines.append("\(Self.backendLabel(configuredBackend)) was unavailable, so this fallback stayed local through \(Self.backendLabel(effectiveBackend)). I did not send the email to Groq or Codex.")
                    } else if let backend = object["email_summary_effective_backend"]?.stringValue, !backend.isEmpty {
                        lines.append("This summary stayed local through \(Self.backendLabel(backend)). I did not send the email to Groq or Codex.")
                    } else {
                        lines.append("This summary stayed local. I did not send the email to Groq or Codex.")
                    }
                }
                return lines.joined(separator: "\n")
            }
            for (index, row) in rows.enumerated() {
                let sender = row["sender"]?.stringValue ?? "Unknown sender"
                let subject = row["subject"]?.stringValue ?? "(no subject)"
                let received = row["received"]?.stringValue ?? ""
                let readState = row["read_state"]?.stringValue ?? "unknown"
                let snippet = row["snippet"]?.stringValue ?? ""
                let suffix = received.isEmpty ? "" : " · \(received)"
                lines.append("\(index + 1). \(sender): \(subject)\(suffix) · \(readState)")
                if !snippet.isEmpty {
                    lines.append("Summary: \(snippet)")
                }
            }
            if let warning = Self.injectionWarning(from: object) {
                lines.append(warning)
            }
            lines.append("This is local \(mailbox) metadata/snippet reading. I did not send the email to a model.")
            return lines.joined(separator: "\n")
        }

        var lines = [object["reply"]?.stringValue ?? "I could not complete the Outlook check yet."]
        if let error = object["error"]?.stringValue, !error.isEmpty {
            lines.append("Error: \(error)")
        }
        if status == "screen_capture_failed",
           let worker = object["worker_process"]?.objectValue {
            let bundle = worker["python_app_bundle"]?.stringValue
            let executable = worker["python_executable"]?.stringValue
            let target = bundle ?? executable
            if let target, !target.isEmpty {
                lines.append("Permission target: \(target)")
            }
        }
        if status == "native_capture_failed" {
            if let preflight = object["screen_access_preflight"]?.boolValue {
                lines.append("Screen preflight: \(preflight ? "granted" : "not granted")")
            }
            if let bundle = object["app_bundle_path"]?.stringValue, !bundle.isEmpty {
                lines.append("App bundle: \(bundle)")
            }
            if let bundleID = object["bundle_identifier"]?.stringValue, !bundleID.isEmpty {
                lines.append("Bundle ID: \(bundleID)")
            }
        }
        let nextSteps = object["next_steps"]?.arrayValue?.compactMap(\.stringValue) ?? []
        if !nextSteps.isEmpty {
            lines.append("Next:")
            for step in nextSteps {
                lines.append("- \(step)")
            }
        }
        return lines.joined(separator: "\n")
    }

    private static func injectionWarning(from object: [String: JSONValue]) -> String? {
        guard let scan = object["injection_scan"]?.objectValue,
              scan["status"]?.stringValue == "flagged" else {
            return nil
        }
        let labels = scan["findings"]?.arrayValue?
            .compactMap { $0.objectValue?["label"]?.stringValue }
            .filter { !$0.isEmpty } ?? []
        if labels.isEmpty {
            return "Warning: this email text matched Jarvis prompt-injection rules. I treated it as untrusted content, not instructions."
        }
        return "Warning: this email text matched Jarvis prompt-injection rules: \(labels.joined(separator: ", ")). I treated it as untrusted content, not instructions."
    }

    private static func mailSelectionIntro(
        mailbox: String,
        scanned: Int,
        unreadCount: Int,
        selectedCount: Int,
        selectionMode: String
    ) -> String {
        if selectionMode == "unread" {
            if unreadCount > selectedCount {
                return "I checked \(mailbox), scanned \(scanned) recent messages, and found \(unreadCount) unread. I am showing the newest \(selectedCount)."
            }
            if selectedCount == 1 {
                return "I checked \(mailbox), scanned \(scanned) recent messages, and found 1 unread message."
            }
            return "I checked \(mailbox), scanned \(scanned) recent messages, and found \(selectedCount) unread messages."
        }
        return "I checked \(mailbox), scanned \(scanned) recent messages, and found no unread messages, so I selected the newest inbox email."
    }

    private func render(_ response: CommandResponse) -> String {
        var lines: [String] = []
        lines.append("Command: \(response.command ?? command)")
        lines.append("Tool: \(response.tool ?? "unknown")")
        lines.append("Executed: \(response.executed.map(String.init) ?? "unknown")")
        lines.append("Summary: \(response.summary ?? "No summary")")
        let timingLabel = Self.timingLabel(for: response.tool)
        if let timing = response.result?.objectValue?["duration_human"]?.stringValue, !timing.isEmpty {
            lines.append("\(timingLabel): \(timing)")
        } else if let seconds = response.result?.objectValue?["duration_seconds"]?.doubleValue {
            lines.append(String(format: "\(timingLabel): %.1fs", seconds))
        }
        let firstVisibleTokenSeconds = response.result?.objectValue?["first_visible_token_seconds"]?.doubleValue
            ?? response.result?.objectValue?["first_token_seconds"]?.doubleValue
        if let firstVisibleTokenSeconds {
            lines.append(String(format: "First visible text: %.1fs", firstVisibleTokenSeconds))
        }

        if let assessment = response.assessment {
            lines.append("")
            lines.append("Risk: \(assessment.riskLabel) (\(assessment.riskLevel))")
            lines.append("Decision: \(assessment.decision)")
            if !assessment.reasons.isEmpty {
                lines.append("Reasons:")
                for reason in assessment.reasons {
                    lines.append("- \(reason)")
                }
            }
        }

        if let confirmation = response.confirmation, confirmation.required {
            lines.append("")
            lines.append("Confirmation: \(confirmation.title) [\(confirmation.kind)]")
            if let exactPhrase = confirmation.exactPhrase {
                lines.append("Exact phrase: \(exactPhrase)")
            }
        }

        if let auditEventId = response.auditEventId {
            lines.append("")
            lines.append("Audit event: \(auditEventId)")
        }

        return lines.joined(separator: "\n")
    }

    private static func formatUptime(_ seconds: Double) -> String {
        let totalSeconds = max(0, Int(seconds.rounded()))
        let minutes = totalSeconds / 60
        let remainingSeconds = totalSeconds % 60
        if minutes > 0 {
            return "\(minutes)m \(remainingSeconds)s"
        }
        return "\(remainingSeconds)s"
    }

    private static func formatDuration(_ seconds: Int) -> String {
        if seconds < 60 {
            return "\(seconds) second\(seconds == 1 ? "" : "s")"
        }
        if seconds < 3600 {
            let minutes = seconds / 60
            let remainingSeconds = seconds % 60
            var text = "\(minutes) minute\(minutes == 1 ? "" : "s")"
            if remainingSeconds > 0 {
                text += " \(remainingSeconds) second\(remainingSeconds == 1 ? "" : "s")"
            }
            return text
        }
        let hours = seconds / 3600
        let minutes = (seconds % 3600) / 60
        var text = "\(hours) hour\(hours == 1 ? "" : "s")"
        if minutes > 0 {
            text += " \(minutes) minute\(minutes == 1 ? "" : "s")"
        }
        return text
    }

    private static func formatVerification(_ verification: VerificationSummary?) -> String {
        guard let verification, verification.available else {
            return "Verification not available"
        }
        let state = verification.ok == true ? "passed" : "failed"
        let passed = verification.passed ?? 0
        let total = verification.total ?? 0
        let age = verification.ageHuman.map { ", \($0) old" } ?? ""
        return "Verification \(state) \(passed)/\(total)\(age)"
    }

    private static func formatCodexActivity(_ activity: CodexActivityResponse) -> String {
        guard let job = activity.latestJob else {
            return "No Codex activity yet"
        }
        let phase = job.phase ?? job.status ?? "unknown"
        var parts = ["\(job.jobId) \(phase)"]
        if let duration = job.durationHuman, !duration.isEmpty {
            parts.append(duration)
        } else if activity.runningCount > 0 {
            parts.append("running")
        }
        if let model = job.model, !model.isEmpty {
            parts.append(model)
        }
        return parts.joined(separator: " | ")
    }

    private static func healthDiagnostics(from health: HealthResponse) -> [String: Any] {
        var payload: [String: Any] = [
            "ok": health.ok,
            "project_root": health.status.projectRoot,
            "python": health.status.python,
            "platform": health.status.platform,
            "machine": health.status.machine,
            "codex": [
                "path": jsonOrNull(health.status.codex.path),
                "version": jsonOrNull(health.status.codex.version),
            ],
        ]
        if let runtime = health.status.runtime {
            payload["runtime"] = runtimeDiagnostics(runtime)
        }
        if let timers = health.status.timers {
            payload["timers"] = [
                "active_count": jsonOrNull(timers.activeCount),
            ]
        }
        if let codexJobs = health.status.codexJobs {
            payload["codex_jobs"] = [
                "tracked_count": jsonOrNull(codexJobs.trackedCount),
                "running_count": jsonOrNull(codexJobs.runningCount),
                "latest_job_id": jsonOrNull(codexJobs.latestJobId),
                "latest_status": jsonOrNull(codexJobs.latestStatus),
            ]
        }
        if let fastModel = health.status.fastModel {
            payload["fast_model"] = fastModelDiagnostics(fastModel)
        }
        if let mode = health.mode {
            payload["mode"] = modeDiagnostics(mode)
        }
        return payload
    }

    private static func readinessDiagnostics(from readiness: ReadinessResponse) -> [String: Any] {
        var payload: [String: Any] = [
            "ok": readiness.ok,
            "generated_at": readiness.generatedAt,
            "tools": [
                "available": readiness.tools.available,
                "total": readiness.tools.total,
                "unavailable_ids": readiness.tools.unavailableIds,
            ],
            "self_check": [
                "ok": readiness.selfCheck.ok,
                "passed": readiness.selfCheck.passed,
                "total": readiness.selfCheck.total,
                "failed": readiness.selfCheck.failed,
            ],
            "audit": [
                "event_count": readiness.audit.eventCount,
                "byte_size_human": readiness.audit.byteSizeHuman,
                "retention_days": readiness.audit.retentionDays,
                "max_bytes_human": readiness.audit.maxBytesHuman,
                "raw_audio_or_screenshots": readiness.audit.rawAudioOrScreenshots,
            ],
            "notes": readiness.notes,
        ]
        if let runtime = readiness.worker.runtime {
            payload["worker_runtime"] = runtimeDiagnostics(runtime)
        }
        if let verification = readiness.verification {
            payload["verification"] = verificationDiagnostics(verification)
        }
        return payload
    }

    private static func codexActivityDiagnostics(_ activity: CodexActivityResponse?) -> [String: Any] {
        guard let activity else {
            return [
                "available": false,
                "reason": "not_loaded",
            ]
        }
        return [
            "available": true,
            "status": activity.status,
            "tracked_count": activity.trackedCount,
            "running_count": activity.runningCount,
            "latest_job": activity.latestJob.map(Self.codexActivityJobDiagnostics) ?? NSNull(),
            "jobs": activity.jobs.map(Self.codexActivityJobDiagnostics),
        ]
    }

    private static func codexActivityJobDiagnostics(_ job: CodexActivityJob) -> [String: Any] {
        [
            "job_id": job.jobId,
            "status": jsonOrNull(job.status),
            "phase": jsonOrNull(job.phase),
            "model": jsonOrNull(job.model),
            "prompt_summary": jsonOrNull(job.promptSummary),
            "started_at": jsonOrNull(job.startedAt),
            "completed_at": jsonOrNull(job.completedAt),
            "last_activity_at": jsonOrNull(job.lastActivityAt),
            "duration_human": jsonOrNull(job.durationHuman),
            "duration_seconds": jsonOrNull(job.durationSeconds),
            "returncode": jsonOrNull(job.returncode),
            "command_preview": jsonOrNull(job.commandPreview),
            "cli_tail": jsonOrNull(job.cliTail),
            "conversation_tail": jsonOrNull(job.conversationTail),
            "reply_tail": jsonOrNull(job.replyTail),
        ]
    }

    private static func permissionDiagnostics(_ permissions: [PermissionReadiness]) -> [[String: Any]] {
        permissions.map { permission in
            [
                "id": permission.id,
                "label": permission.label,
                "state": permission.state,
                "detail": permission.detail,
                "is_ready": permission.isReady,
            ]
        }
    }

    private static func commandDiagnostics(from response: CommandResponse) -> [String: Any] {
        var payload: [String: Any] = [
            "command": jsonOrNull(response.command),
            "tool": jsonOrNull(response.tool),
            "summary": jsonOrNull(response.summary),
            "executed": jsonOrNull(response.executed),
            "audit_event_id": jsonOrNull(response.auditEventId),
        ]
        if let result = response.result {
            payload["result"] = result.anyValue
        }
        if let speech = response.speech {
            payload["speech"] = speech.anyValue
        }
        if let assessment = response.assessment {
            payload["assessment"] = [
                "risk_level": assessment.riskLevel,
                "risk_label": assessment.riskLabel,
                "decision": assessment.decision,
                "requires_confirmation": assessment.requiresConfirmation,
                "requires_typed_confirmation": assessment.requiresTypedConfirmation,
                "blocked": assessment.blocked,
                "reasons": assessment.reasons,
            ]
        }
        if let confirmation = response.confirmation {
            payload["confirmation"] = [
                "required": confirmation.required,
                "kind": confirmation.kind,
                "title": confirmation.title,
                "message": jsonOrNull(confirmation.message),
                "exact_phrase": jsonOrNull(confirmation.exactPhrase),
                "prototype_note": jsonOrNull(confirmation.prototypeNote),
            ]
        }
        return payload
    }

    private static func turnEvent(_ phase: String, startedAt: Date, detail: String?) -> [String: Any] {
        var payload: [String: Any] = [
            "phase": phase,
            "elapsed_seconds": max(0, Date().timeIntervalSince(startedAt)),
        ]
        if let detail, !detail.isEmpty {
            payload["detail"] = detail
        }
        return payload
    }

    private static func turnTrace(
        command: String,
        startedAt: Date,
        events: [[String: Any]],
        visibleStatusLines: [String],
        finalVisibleText: String,
        finalSpeech: Any,
        routeSource: String?,
        modelBackend: String?,
        modelName: String?,
        state: String,
        tool: String
    ) -> [String: Any] {
        [
            "schema": "jarvis.turn_trace.v1",
            "command_preview": redactChatExportText(String(command.prefix(240))),
            "total_elapsed_seconds": max(0, Date().timeIntervalSince(startedAt)),
            "current_phase": state == "Error" ? "Error" : (state == "Approval" ? "Approval" : "Done"),
            "events": events,
            "visible_status_lines": visibleStatusLines.map(redactChatExportText),
            "final_visible_text": redactChatExportText(finalVisibleText),
            "final_answer_visible": !finalVisibleText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
            "final_speech": finalSpeech,
            "route_source": jsonOrNull(routeSource),
            "model_backend": jsonOrNull(modelBackend),
            "model_name": jsonOrNull(modelName),
            "final_state": state,
            "final_tool": tool,
        ]
    }

    private static func routeSource(from response: CommandResponse) -> String? {
        response.result?.objectValue?["routing"]?.objectValue?["source"]?.stringValue
            ?? response.result?.objectValue?["route_source"]?.stringValue
            ?? response.result?.objectValue?["selection_source"]?.stringValue
    }

    private static func modelBackend(from response: CommandResponse) -> String? {
        response.result?.objectValue?["backend"]?.stringValue
            ?? response.result?.objectValue?["email_summary_effective_backend"]?.stringValue
            ?? response.result?.objectValue?["email_summary_backend"]?.stringValue
    }

    private static func modelName(from response: CommandResponse) -> String? {
        response.result?.objectValue?["model"]?.stringValue
            ?? response.result?.objectValue?["email_summary_model"]?.stringValue
    }

    private static func runtimeDiagnostics(_ runtime: RuntimeStatus) -> [String: Any] {
        [
            "pid": runtime.pid,
            "cwd": runtime.cwd,
            "source": runtime.source,
            "started_at": runtime.startedAt,
            "uptime_seconds": runtime.uptimeSeconds,
        ]
    }

    private static func fastModelDiagnostics(_ fastModel: FastModelStatus) -> [String: Any] {
        [
            "backend": jsonOrNull(fastModel.backend),
            "model": jsonOrNull(fastModel.model),
            "available": jsonOrNull(fastModel.available),
            "fallback_enabled": jsonOrNull(fastModel.fallbackEnabled),
            "fallback_backend": jsonOrNull(fastModel.fallbackBackend),
            "fallback_model": jsonOrNull(fastModel.fallbackModel),
            "timeout_seconds": jsonOrNull(fastModel.timeoutSeconds),
            "max_tokens": jsonOrNull(fastModel.maxTokens),
            "groq_key_configured": jsonOrNull(fastModel.groqKeyConfigured),
            "groq_base_url": jsonOrNull(fastModel.groqBaseUrl),
            "ollama_path": jsonOrNull(fastModel.ollamaPath),
            "ollama_base_url": jsonOrNull(fastModel.ollamaBaseUrl),
        ]
    }

    private static func modeDiagnostics(_ mode: ModeResponse) -> [String: Any] {
        [
            "paused": mode.paused,
            "reason": mode.reason,
            "updated_at": mode.updatedAt,
            "commands_enabled": mode.commandsEnabled,
        ]
    }

    private static func verificationDiagnostics(_ verification: VerificationSummary) -> [String: Any] {
        [
            "available": verification.available,
            "path": jsonOrNull(verification.path),
            "ok": jsonOrNull(verification.ok),
            "passed": jsonOrNull(verification.passed),
            "total": jsonOrNull(verification.total),
            "generated_at": jsonOrNull(verification.generatedAt),
            "age_seconds": jsonOrNull(verification.ageSeconds),
            "age_human": jsonOrNull(verification.ageHuman),
        ]
    }

    private static func jsonOrNull<T>(_ value: T?) -> Any {
        value ?? NSNull()
    }

    private static func redactedJSONValue(_ value: Any) -> Any {
        if let string = value as? String {
            return redactChatExportText(string)
        }
        if let dictionary = value as? [String: Any] {
            var redacted: [String: Any] = [:]
            for (key, item) in dictionary {
                redacted[key] = redactedJSONValue(item)
            }
            return redacted
        }
        if let array = value as? [Any] {
            return array.map(redactedJSONValue)
        }
        return value
    }

    private static func redactChatExportText(_ text: String) -> String {
        var redacted = regexReplace(
            text,
            pattern: #"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"#,
            replacement: "[SESSION_ID_HIDDEN]"
        )
        let trimmed = redacted.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.range(of: #"^\d{4,12}$"#, options: .regularExpression) != nil || textLooksLikeCodeContext(trimmed) {
            redacted = regexReplace(redacted, pattern: #"\b\d{4,12}\b"#, replacement: "[CODE_HIDDEN]")
        }
        return redacted
    }

    private static func textLooksLikeCodeContext(_ text: String) -> Bool {
        let lower = text.lowercased()
        let cues = ["secret code", "confirmation code", "authorization code", "approval code", "same codex", "tell codex"]
        return cues.contains { lower.contains($0) }
    }

    private static func regexReplace(_ text: String, pattern: String, replacement: String) -> String {
        do {
            let regex = try NSRegularExpression(pattern: pattern)
            let range = NSRange(text.startIndex..<text.endIndex, in: text)
            return regex.stringByReplacingMatches(in: text, range: range, withTemplate: replacement)
        } catch {
            return text
        }
    }

    private static func timingLabel(for tool: String?) -> String {
        switch tool {
        case "codex.delegate", "codex.job", "conversation.codex":
            return "Codex time"
        case "conversation.fast_local":
            return "Fast model time"
        case "quick.local_control":
            return "Local command time"
        default:
            return "Tool time"
        }
    }

    private static func backendLabel(_ backend: String) -> String {
        switch backend.lowercased() {
        case "groq":
            return "Groq"
        case "ollama":
            return "Ollama"
        default:
            return backend
        }
    }

    private static func permissionStatusReply(_ permissions: [PermissionReadiness]) -> String {
        let target = permissionTargetDiagnostics()
        var lines = [
            "Permission target: \(target["path"] ?? "unknown")",
            "Bundle ID: \(target["bundle_id"] ?? "unknown")",
            "Permissions: \(JarvisPermissionService.summary(permissions))",
        ]
        for permission in permissions {
            lines.append("- \(permission.label): \(permission.state). \(permission.detail)")
        }
        let missing = permissions.filter { !$0.isReady }
        if !missing.isEmpty {
            lines.append("Missing: \(missing.map(\.label).joined(separator: ", ")).")
            lines.append("Use System Settings > Privacy & Security to grant missing permissions to the current Jarvis app.")
        }
        return lines.joined(separator: "\n")
    }

    private static func permissionTargetDiagnostics() -> [String: String] {
        [
            "path": Bundle.main.bundleURL.path,
            "bundle_id": Bundle.main.bundleIdentifier ?? "unknown",
        ]
    }

    private static func progressReplies(for _: String) -> [(delayNanoseconds: UInt64, text: String)] {
        return [
            (5_000_000_000, "Still working. Wait a sec..."),
            (15_000_000_000, "This is taking longer than usual; I am still on it."),
        ]
    }

    static func shouldUseNativeHotKeyStatus(_ commandText: String) -> Bool {
        let lower = commandText.lowercased()
        guard lower.contains("hotkey") || lower.contains("shortcut") || lower.contains("keyboard wake") else {
            return false
        }
        let mutationCues = [
            "assign",
            "change",
            "configure",
            "edit",
            "rebind",
            "set",
            "update",
        ]
        guard !mutationCues.contains(where: { lower.contains($0) }) else {
            return false
        }
        let statusCues = [
            "status",
            "check",
            "show",
            "what",
            "which",
            "keyboard",
            "shortcut",
            "hotkey",
        ]
        return statusCues.contains(where: { lower.contains($0) })
    }

    static func shouldUseNativeVoiceStatus(_ commandText: String) -> Bool {
        let lower = commandText.lowercased()
        let ttsOutputCues = [
            "tts",
            "text-to-speech",
            "text to speech",
            "speech output",
            "spoken reply",
            "spoken replies",
            "speak status",
            "can you speak",
            "voice output",
        ]
        guard !ttsOutputCues.contains(where: { lower.contains($0) }) else {
            return false
        }
        let voiceCues = [
            "voice",
            "speech",
            "microphone wake",
            "voice input",
            "speech-to-text",
            "speech to text",
            "stt",
        ]
        guard voiceCues.contains(where: { lower.contains($0) }) else {
            return false
        }
        let mutationCues = [
            "allow",
            "ask",
            "change",
            "configure",
            "enable",
            "grant",
            "request",
            "set",
            "start",
            "turn on",
        ]
        guard !mutationCues.contains(where: { lower.contains($0) }) else {
            return false
        }
        let statusCues = [
            "available",
            "check",
            "ready",
            "show",
            "status",
            "what",
            "which",
        ]
        return statusCues.contains(where: { lower.contains($0) })
    }

    static func shouldUseNativeTestStatus(_ commandText: String) -> Bool {
        let lower = commandText.lowercased()
        let testCues = [
            "copy tests",
            "smoke test",
            "smoke tests",
            "test list",
            "test prompts",
            "test status",
            "what should i test",
            "what to test",
        ]
        guard testCues.contains(where: { lower.contains($0) }) else {
            return false
        }
        let mutationCues = [
            "change",
            "delete",
            "edit",
            "remove",
            "set",
            "update",
        ]
        guard !mutationCues.contains(where: { lower.contains($0) }) else {
            return false
        }
        let statusCues = [
            "check",
            "copy",
            "list",
            "show",
            "status",
            "what",
        ]
        return statusCues.contains(where: { lower.contains($0) })
    }

    static func shouldUseNativeScreenStatus(_ commandText: String) -> Bool {
        let lower = commandText.lowercased()
        let screenCues = [
            "screen status",
            "screen capture status",
            "screenshot status",
            "ocr status",
            "native ocr status",
            "screen readiness",
        ]
        guard screenCues.contains(where: { lower.contains($0) }) else {
            return false
        }
        let mutationCues = [
            "capture",
            "read the visible",
            "scan",
            "take",
        ]
        guard !mutationCues.contains(where: { lower.contains($0) }) else {
            return false
        }
        let statusCues = [
            "check",
            "ready",
            "readiness",
            "show",
            "status",
            "what",
            "which",
        ]
        return statusCues.contains(where: { lower.contains($0) })
    }

    static func shouldUseNativePermissionStatus(_ commandText: String) -> Bool {
        let lower = commandText.lowercased()
        guard lower.contains("permission")
            || lower.contains("screen recording")
            || lower.contains("accessibility")
            || lower.contains("microphone")
            || lower.contains("speech recognition")
            || lower.contains("notification") else {
            return false
        }
        let statusCues = [
            "status",
            "check",
            "show",
            "list",
            "diagnostic",
            "diagnostics",
            "why",
            "ready",
            "granted",
        ]
        return statusCues.contains(where: { lower.contains($0) })
    }

    static func shouldUseNativeOutlookRead(_ commandText: String) -> Bool {
        let lower = commandText.lowercased()
        guard mentionsMail(lower) else {
            return false
        }
        if hasBlockedMailAction(lower) {
            return false
        }
        guard hasVisualMailCue(lower) else {
            return false
        }
        let readCues = [
            "check",
            "describe",
            "extract",
            "read",
            "scan",
            "what",
            "summarize",
            "summary",
        ]
        return readCues.contains(where: { lower.contains($0) }) || lower.contains("ocr")
    }

    private static func mentionsMail(_ lower: String) -> Bool {
        lower.contains("outlook") || lower.contains("email") || lower.contains("mail") || lower.contains("inbox")
    }

    private static func hasBlockedMailAction(_ lower: String) -> Bool {
        let blockedActions = [
            "send",
            "reply",
            "forward",
            "delete",
            "archive",
            "move",
            "draft",
            "download",
            "attachment",
            "attach",
            "mark",
            "junk",
            "unsubscribe",
        ]
        return blockedActions.contains(where: { lower.contains($0) })
    }

    private static func hasVisualMailCue(_ lower: String) -> Bool {
        let visualCues = [
            "visible",
            "screen",
            "screenshot",
            "ocr",
            "window",
            "frontmost",
            "front-most",
            "read the screen",
            "read visible",
            "on screen",
        ]
        return visualCues.contains(where: { lower.contains($0) })
    }

    private static func shouldTryNativeMailFallback(_ response: CommandResponse) -> Bool {
        guard response.confirmation?.required != true,
              response.tool == "outlook.visible_summary",
              let object = response.result?.objectValue else {
            return false
        }
        let status = object["status"]?.stringValue ?? ""
        let source = object["source"]?.stringValue ?? ""
        if status != "checked" {
            return true
        }
        return source == "screen_ocr" || source == "fallback_failed"
    }

    private static func nativeMailFallbackIsUseful(_ response: CommandResponse) -> Bool {
        guard response.tool == "outlook.visible_summary",
              let object = response.result?.objectValue else {
            return false
        }
        return object["status"]?.stringValue == "checked"
    }

    private static func mailboxLabel(for source: String) -> String {
        switch source {
        case "apple_mail":
            return "Apple Mail"
        case "sqlite":
            return "Outlook local database"
        default:
            return "Outlook"
        }
    }
}

enum ShellModelError: Error, CustomStringConvertible {
    case workerUnavailable(String)
    case exportFailed(String)

    var description: String {
        switch self {
        case .workerUnavailable(let message):
            return message
        case .exportFailed(let message):
            return message
        }
    }
}

struct ChatMessage: Identifiable, Equatable {
    let id: UUID
    let role: ChatRole
    let text: String
    let detail: String?

    init(id: UUID = UUID(), role: ChatRole, text: String, detail: String? = nil) {
        self.id = id
        self.role = role
        self.text = text
        self.detail = detail
    }
}

enum ChatRole: String, Equatable {
    case user
    case jarvis
    case system
}
