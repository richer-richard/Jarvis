import Foundation
import JarvisClient
#if canImport(Speech)
@preconcurrency import Speech
#endif

enum JarvisMenuBarSelfTest {
    @MainActor
    static func run() async throws {
        let client = try JarvisClient.fromEnvironment()
        let supervisor = JarvisWorkerSupervisor(client: client)
        let startup = await supervisor.ensureRunning()
        defer {
            if startup == .started {
                supervisor.stopStartedWorker()
            }
        }
        guard startup.isReady else {
            throw SelfTestError.failed("Worker startup failed: \(startup.description)")
        }

        let health = try await client.health()
        guard health.ok else {
            throw SelfTestError.failed("Worker health endpoint did not report ok.")
        }
        try runCommandRoutingSelfTest()

        var modeSelfTest = false
        if let mode = try? await client.mode() {
            guard mode.commandsEnabled else {
                throw SelfTestError.failed("Worker started in paused mode; resume Jarvis before running the default self-test.")
            }
            let paused = try await client.setPaused(true, reason: "Menu-bar self-test pause.")
            guard paused.paused, paused.commandsEnabled == false else {
                _ = try? await client.setPaused(false, reason: "Menu-bar self-test cleanup.")
                throw SelfTestError.failed("Pause mode did not report paused.")
            }
            do {
                let pausedStatus = try await client.send(command: "status")
                guard pausedStatus.tool == "policy.pause", pausedStatus.executed == false else {
                    _ = try? await client.setPaused(false, reason: "Menu-bar self-test cleanup.")
                    throw SelfTestError.failed("Paused worker did not block status command.")
                }
                let resumed = try await client.setPaused(false, reason: "Menu-bar self-test resume.")
                guard resumed.paused == false, resumed.commandsEnabled else {
                    _ = try? await client.setPaused(false, reason: "Menu-bar self-test cleanup.")
                    throw SelfTestError.failed("Pause mode did not resume command execution.")
                }
            } catch {
                _ = try? await client.setPaused(false, reason: "Menu-bar self-test cleanup.")
                throw error
            }
            modeSelfTest = true
        }

        let status = try await client.send(command: "status")
        guard status.tool == "system.status", status.executed == true else {
            throw SelfTestError.failed("Status command did not execute through system.status.")
        }

        let dangerous = try await client.send(command: "shell: rm -rf /tmp/example")
        guard dangerous.tool == "policy.strong_confirmation",
              dangerous.executed == false,
              dangerous.confirmation?.exactPhrase == "JARVIS APPROVE" else {
            throw SelfTestError.failed("Dangerous command did not stop at strong confirmation.")
        }

        let audit = try await client.auditStatus()
        guard audit.retentionDays == 90, audit.maxBytes > 0 else {
            throw SelfTestError.failed("Audit status did not report the expected retention policy.")
        }
        let readiness = try await client.readiness()
        let verification = readiness.verification

        print("Jarvis menu-bar self-test passed")
        print("Worker startup: \(startup.description)")
        print("Worker: \(health.status.platform)")
        print("Codex: \(health.status.codex.version ?? "not detected")")
        print("Audit: \(audit.eventCount) events, \(audit.byteSizeHuman), cap \(audit.maxBytesHuman)")
        if let verification, verification.available {
            let state = verification.ok == true ? "passed" : "failed"
            print("Verification: \(state) \(verification.passed ?? 0)/\(verification.total ?? 0)")
        } else {
            print("Verification: not available")
        }
        print("Mode: \(modeSelfTest ? "pause/resume passed" : "endpoint not available")")
    }

    @MainActor
    static func runCommandRoutingSelfTest() throws {
        guard !JarvisShellModel.shouldUseNativeOutlookRead("check my email and summarize the newest email in my inbox") else {
            throw SelfTestError.failed("Generic email requests should go to the worker planner before native OCR.")
        }
        guard JarvisShellModel.shouldUseNativeOutlookRead("read the visible Outlook screen with OCR") else {
            throw SelfTestError.failed("Explicit visible Outlook OCR requests should use native OCR.")
        }
        guard !JarvisShellModel.shouldUseNativeOutlookRead("send an email with a screenshot") else {
            throw SelfTestError.failed("Blocked email actions must not use native read routing.")
        }
        guard JarvisShellModel.shouldUseNativePermissionStatus("permissions status") else {
            throw SelfTestError.failed("Permission status should use the native Swift permission snapshot.")
        }
        guard !JarvisShellModel.shouldUseNativePermissionStatus("grant microphone permission") else {
            throw SelfTestError.failed("Permission-granting requests must not be treated as a read-only status command.")
        }
        guard JarvisShellModel.shouldUseNativeHotKeyStatus("hotkey status") else {
            throw SelfTestError.failed("Hotkey status should use the native Swift hotkey snapshot.")
        }
        guard JarvisShellModel.shouldUseNativeHotKeyStatus("which keyboard shortcut wakes Jarvis") else {
            throw SelfTestError.failed("Keyboard shortcut status should use the native Swift hotkey snapshot.")
        }
        guard !JarvisShellModel.shouldUseNativeHotKeyStatus("change the Jarvis shortcut") else {
            throw SelfTestError.failed("Hotkey mutation requests must not be treated as a read-only status command.")
        }
        guard JarvisMenuBarApp.activationPolicy(environment: [:]) == .regular else {
            throw SelfTestError.failed("Jarvis should show the Dock icon by default.")
        }
        guard JarvisMenuBarApp.activationPolicy(environment: ["JARVIS_SHOW_DOCK_ICON": "no"]) == .accessory else {
            throw SelfTestError.failed("Debug Dock-icon override should allow accessory activation policy.")
        }
        guard JarvisAppDelegate.menuBarItemEnabled(environment: [:]) else {
            throw SelfTestError.failed("Menu-bar item should be enabled by default beside normal Dock app mode.")
        }
        guard !JarvisAppDelegate.menuBarItemEnabled(environment: ["JARVIS_SHOW_MENU_BAR_ITEM": "no"]) else {
            throw SelfTestError.failed("Menu-bar item override should allow hiding the status item.")
        }
        guard JarvisAppDelegate.menuBarItemEnabled(environment: ["JARVIS_SHOW_MENU_BAR_ITEM": "on"]) else {
            throw SelfTestError.failed("Menu-bar item override should allow enabling the status item.")
        }
        guard JarvisAppDelegate.speechMuteMenuTitle(muted: false) == "Shut Up" else {
            throw SelfTestError.failed("Unmuted menu title should be Shut Up.")
        }
        guard JarvisAppDelegate.speechMuteMenuTitle(muted: true) == "Keep Blabbering" else {
            throw SelfTestError.failed("Muted menu title should be Keep Blabbering.")
        }
        guard JarvisAppDelegate.wakeListenerMenuTitle(listening: false) == "Start Hey Jarvis" else {
            throw SelfTestError.failed("Stopped wake listener menu title should be Start Hey Jarvis.")
        }
        guard JarvisAppDelegate.wakeListenerMenuTitle(listening: true) == "Stop Hey Jarvis" else {
            throw SelfTestError.failed("Running wake listener menu title should be Stop Hey Jarvis.")
        }
        let wakeCases: [(transcript: String, detected: Bool, command: String)] = [
            ("Hey Jarvis check email", true, "check email"),
            ("hey jervis please check email", true, "check email"),
            ("okay jervis please check status", true, "check status"),
            ("hey jars please check email", false, ""),
            ("please check email later", false, ""),
        ]
        for wakeCase in wakeCases {
            let actual = JarvisWakeListener.testDetectWake(wakeCase.transcript)
            guard actual.detected == wakeCase.detected, actual.command == wakeCase.command else {
                throw SelfTestError.failed(
                    "Wake detector mismatch for \(wakeCase.transcript): detected=\(actual.detected), command=\(actual.command)"
                )
            }
        }
        let score = JarvisWakeListener.testWakeScore("okay jervis please check status")
        guard score["detected"] == "true", score["phrase"] == "okay jarvis", score["command"] == "check status" else {
            throw SelfTestError.failed("Wake score diagnostics should explain fuzzy okay jarvis detection.")
        }
        guard !JarvisShellModel.shouldUseNativeVoiceStatus("tts status") else {
            throw SelfTestError.failed("TTS status should route to backend diagnostics.tts, not the native voice snapshot.")
        }
        guard !JarvisShellModel.shouldUseNativeVoiceStatus("can you speak") else {
            throw SelfTestError.failed("Natural TTS readiness questions should route to backend diagnostics.tts.")
        }
        guard !JarvisShellModel.shouldUseNativeVoiceStatus("voice output status") else {
            throw SelfTestError.failed("Voice-output readiness should route to backend diagnostics.tts.")
        }
        guard JarvisShellModel.shouldUseNativeVoiceStatus("voice status") else {
            throw SelfTestError.failed("Voice status should use the native Swift voice snapshot.")
        }
        guard JarvisShellModel.shouldUseNativeVoiceStatus("is speech-to-text ready") else {
            throw SelfTestError.failed("Speech-to-text readiness should use the native Swift voice snapshot.")
        }
        guard !JarvisShellModel.shouldUseNativeVoiceStatus("enable voice input") else {
            throw SelfTestError.failed("Voice mutation requests must not be treated as a read-only status command.")
        }
        guard JarvisShellModel.shouldUseNativeTestStatus("test status") else {
            throw SelfTestError.failed("Test status should use the native Swift test-list snapshot.")
        }
        guard JarvisShellModel.shouldUseNativeTestStatus("what should I test") else {
            throw SelfTestError.failed("Natural test-list questions should use the native Swift test-list snapshot.")
        }
        guard !JarvisShellModel.shouldUseNativeTestStatus("update the test list") else {
            throw SelfTestError.failed("Test-list mutation requests must not be treated as a read-only status command.")
        }
        guard JarvisShellModel.shouldUseNativeScreenStatus("screen status") else {
            throw SelfTestError.failed("Screen status should use the native Swift screen snapshot.")
        }
        guard !JarvisShellModel.shouldUseNativeScreenStatus("read the visible Outlook screen with OCR") else {
            throw SelfTestError.failed("Visible OCR requests must not be treated as read-only screen status.")
        }
        var conversationMessages = [
            ChatMessage(role: .user, text: "Give me a math problem."),
            ChatMessage(role: .jarvis, text: "Solve x + 2 = 5."),
        ]
        conversationMessages.append(
            contentsOf: (0..<14).map { index in
                ChatMessage(role: .jarvis, text: "Still working \(index).", detail: "Working")
            }
        )
        conversationMessages.append(ChatMessage(role: .system, text: "Copied chat JSON."))
        conversationMessages.append(ChatMessage(role: .user, text: "x = 3"))

        let history = JarvisShellModel.conversationHistoryPayload(
            from: conversationMessages,
            currentCommand: "x = 3"
        )
        guard history == [
            ["role": "user", "text": "Give me a math problem."],
            ["role": "assistant", "text": "Solve x + 2 = 5."],
        ] else {
            throw SelfTestError.failed("Conversation history payload did not preserve prior context while skipping current/progress rows.")
        }
    }

    static func runPermissionReadiness() async throws {
        let snapshot = await JarvisPermissionService.snapshot()
        let expectedIds = Set(["microphone", "speech-recognition", "screen-recording", "accessibility", "notifications"])
        let actualIds = Set(snapshot.map(\.id))
        guard actualIds == expectedIds else {
            throw SelfTestError.failed("Permission snapshot missing expected items: \(actualIds.sorted().joined(separator: ", "))")
        }
        guard snapshot.count == expectedIds.count else {
            throw SelfTestError.failed("Permission snapshot contains duplicate or extra rows.")
        }
        let incompleteRows = snapshot.filter { permission in
            permission.label.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                || permission.state.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                || permission.detail.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        }
        guard incompleteRows.isEmpty else {
            throw SelfTestError.failed("Permission snapshot has incomplete rows: \(incompleteRows.map(\.id).joined(separator: ", "))")
        }
        let summary = JarvisPermissionService.summary(snapshot)
        guard summary.contains("/\(expectedIds.count) ready") else {
            throw SelfTestError.failed("Permission summary did not include all readiness rows: \(summary)")
        }

        print("Jarvis permission self-test passed")
        print(summary)
        print("Permission rows: \(snapshot.count)")
        for permission in snapshot {
            print("\(permission.label): \(permission.state)")
        }
    }

    @MainActor
    static func runWakePermissionCallbacks() async throws {
        let authorized = await JarvisWakeListener.testPermissionCallbackPath()
        print("Jarvis wake permission self-test passed")
        print("Wake permission callback returned: \(authorized ? "authorized" : "not authorized")")
    }

    @MainActor
    static func runWakeStartStop() async throws {
        try await runWakeStartStop(durationSeconds: 2.5)
    }

    @MainActor
    static func runWakeStartStop(durationSeconds: Double) async throws {
        let listener = JarvisWakeListener()
        var snapshots: [JarvisWakeListenerSnapshot] = []
        listener.onStateChange = { snapshot in
            snapshots.append(snapshot)
        }
        listener.start()
        try await Task.sleep(nanoseconds: UInt64(max(0.1, durationSeconds) * 1_000_000_000))
        listener.stop()
        guard !snapshots.isEmpty else {
            throw SelfTestError.failed("Wake listener did not publish any state changes.")
        }
        let resettingCount = snapshots.filter { $0.phase == "Resetting" }.count
        guard resettingCount <= 3 else {
            throw SelfTestError.failed("Wake listener restarted too often during soak: \(resettingCount) resets.")
        }
        let phases = snapshots.map(\.phase).joined(separator: ", ")
        print("Jarvis wake start self-test passed")
        print("Wake phases: \(phases)")
        print("Final wake status: \(listener.snapshot.status)")
    }

    static func runSpeechFileTranscription(audioPath: String, outputPath: String) async throws {
        #if canImport(Speech)
        let startedAt = Date()
        let audioURL = URL(fileURLWithPath: audioPath)
        guard FileManager.default.fileExists(atPath: audioURL.path) else {
            try writeJSON(
                [
                    "status": "missing_audio",
                    "authorized": false,
                    "audio_path": audioPath,
                    "transcript": "",
                    "error": "Audio file does not exist.",
                ],
                to: outputPath
            )
            throw SelfTestError.failed("Audio file does not exist: \(audioPath)")
        }

        let authorization = await requestSpeechRecognitionAuthorization()
        guard authorization.status == .authorized else {
            try writeJSON(
                [
                    "status": authorization.timedOut ? "authorization_timeout" : "not_authorized",
                    "authorized": false,
                    "authorization": speechAuthorizationLabel(authorization.status),
                    "authorization_timed_out": authorization.timedOut,
                    "audio_path": audioPath,
                    "transcript": "",
                    "duration_seconds": round(Date().timeIntervalSince(startedAt) * 1000) / 1000,
                ],
                to: outputPath
            )
            print("Jarvis STT file self-test skipped: speech recognition \(speechAuthorizationLabel(authorization.status))")
            return
        }

        guard let recognizer = SFSpeechRecognizer(locale: Locale(identifier: "en-US")) ?? SFSpeechRecognizer(),
              recognizer.isAvailable else {
            try writeJSON(
                [
                    "status": "recognizer_unavailable",
                    "authorized": true,
                    "audio_path": audioPath,
                    "transcript": "",
                    "duration_seconds": round(Date().timeIntervalSince(startedAt) * 1000) / 1000,
                ],
                to: outputPath
            )
            print("Jarvis STT file self-test skipped: recognizer unavailable")
            return
        }

        let transcript = try await transcribeAudioFile(audioURL, recognizer: recognizer)
        try writeJSON(
            [
                "status": "completed",
                "authorized": true,
                "audio_path": audioPath,
                "transcript": transcript,
                "duration_seconds": round(Date().timeIntervalSince(startedAt) * 1000) / 1000,
            ],
            to: outputPath
        )
        print("Jarvis STT file self-test passed")
        print("Transcript: \(transcript)")
        #else
        try writeJSON(
            [
                "status": "speech_framework_unavailable",
                "authorized": false,
                "audio_path": audioPath,
                "transcript": "",
                "error": "Speech framework unavailable in this build.",
            ],
            to: outputPath
        )
        print("Jarvis STT file self-test skipped: Speech framework unavailable")
        #endif
    }

    @MainActor
    static func runWorkerMonitorRecovery() async throws {
        let client = try JarvisClient.fromEnvironment()
        let supervisor = JarvisWorkerSupervisor(client: client)
        let startup = await supervisor.ensureRunning()

        guard startup == .started else {
            if startup == .alreadyRunning {
                print("Jarvis worker monitor self-test skipped")
                print("Worker startup: \(startup.description)")
                print("Use an unused localhost port to exercise restart recovery.")
                return
            }
            throw SelfTestError.failed("Worker startup failed: \(startup.description)")
        }

        guard try await client.health().ok else {
            supervisor.stopStartedWorker()
            throw SelfTestError.failed("Started worker did not report healthy.")
        }

        supervisor.stopStartedWorker()
        guard await waitForHealth(client: client, healthy: false, timeoutSeconds: 8) else {
            throw SelfTestError.failed("Started worker did not stop before recovery check.")
        }

        let recovery = await supervisor.ensureRunning()
        defer {
            if recovery == .started {
                supervisor.stopStartedWorker()
            }
        }
        guard recovery == .started else {
            throw SelfTestError.failed("Worker recovery did not restart the worker: \(recovery.description)")
        }
        guard try await client.health().ok else {
            throw SelfTestError.failed("Recovered worker did not report healthy.")
        }

        print("Jarvis worker monitor self-test passed")
        print("Initial startup: \(startup.description)")
        print("Recovery startup: \(recovery.description)")
    }

    @MainActor
    static func runWorkerStartupConcurrency() async throws {
        let client = try JarvisClient.fromEnvironment()
        let supervisor = JarvisWorkerSupervisor(client: client)

        async let firstStartup = supervisor.ensureRunning()
        async let secondStartup = supervisor.ensureRunning()
        let statuses = await [firstStartup, secondStartup]

        guard statuses.allSatisfy(\.isReady) else {
            throw SelfTestError.failed("Concurrent startup failed: \(statuses.map(\.description).joined(separator: ", "))")
        }
        guard statuses.contains(.started) else {
            if statuses.allSatisfy({ $0 == .alreadyRunning }) {
                print("Jarvis worker concurrency self-test skipped")
                print("Worker startup: Worker already online")
                print("Use an unused localhost port to exercise startup serialization.")
                return
            }
            throw SelfTestError.failed("Concurrent startup did not start a worker: \(statuses.map(\.description).joined(separator: ", "))")
        }
        guard try await client.health().ok else {
            supervisor.stopStartedWorker()
            throw SelfTestError.failed("Concurrent startup worker did not report healthy.")
        }

        supervisor.stopStartedWorker()
        guard await waitForHealth(client: client, healthy: false, timeoutSeconds: 8) else {
            throw SelfTestError.failed("Concurrent startup cleanup left a worker running.")
        }

        print("Jarvis worker concurrency self-test passed")
        print("Startup calls: \(startupSummary(statuses))")
        print("Cleanup: worker stopped")
    }

    @MainActor
    static func runWorkerAutostartDisabled() async throws {
        let client = try JarvisClient.fromEnvironment()
        let supervisor = JarvisWorkerSupervisor(client: client)
        let startup = await supervisor.ensureRunning()
        guard startup == .disabled else {
            supervisor.stopStartedWorker()
            throw SelfTestError.failed("Autostart opt-out did not return disabled: \(startup.description)")
        }

        print("Jarvis worker autostart-disabled self-test passed")
        print("Worker startup: \(startup.description)")
    }

    private static func startupSummary(_ statuses: [WorkerStartupStatus]) -> String {
        let descriptions = statuses.map(\.description)
        if Set(descriptions).count == 1, let first = descriptions.first {
            return "shared result: \(first)"
        }
        return descriptions.joined(separator: " | ")
    }

    private static func waitForHealth(client: JarvisClient, healthy expected: Bool, timeoutSeconds: Double) async -> Bool {
        let deadline = Date().addingTimeInterval(timeoutSeconds)
        while Date() < deadline {
            let healthy: Bool
            do {
                healthy = try await client.health().ok
            } catch {
                healthy = false
            }
            if healthy == expected {
                return true
            }
            try? await Task.sleep(nanoseconds: 200_000_000)
        }
        return false
    }

    static func writeJSON(_ payload: [String: Any], to path: String) throws {
        let url = URL(fileURLWithPath: path)
        try FileManager.default.createDirectory(
            at: url.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        let data = try JSONSerialization.data(withJSONObject: payload, options: [.prettyPrinted, .sortedKeys])
        try data.write(to: url)
    }

    #if canImport(Speech)
    private static func requestSpeechRecognitionAuthorization() async -> SpeechAuthorizationResult {
        let currentStatus = SFSpeechRecognizer.authorizationStatus()
        if currentStatus != .notDetermined {
            return SpeechAuthorizationResult(status: currentStatus, timedOut: false)
        }
        return await withCheckedContinuation { continuation in
            let gate = SpeechAuthorizationGate()
            SFSpeechRecognizer.requestAuthorization { status in
                gate.finish(continuation, result: SpeechAuthorizationResult(status: status, timedOut: false))
            }
            DispatchQueue.global().asyncAfter(deadline: .now() + 8) {
                gate.finish(
                    continuation,
                    result: SpeechAuthorizationResult(status: .notDetermined, timedOut: true)
                )
            }
        }
    }

    private static func transcribeAudioFile(_ audioURL: URL, recognizer: SFSpeechRecognizer) async throws -> String {
        let request = SFSpeechURLRecognitionRequest(url: audioURL)
        request.shouldReportPartialResults = false
        request.taskHint = .dictation

        return try await withCheckedThrowingContinuation { continuation in
            let gate = SpeechTranscriptionGate()
            let task = recognizer.recognitionTask(with: request) { result, error in
                if let error {
                    gate.finish(continuation, result: .failure(error))
                    return
                }
                guard let result, result.isFinal else {
                    return
                }
                gate.finish(continuation, result: .success(result.bestTranscription.formattedString))
            }
            gate.setTask(task)
            DispatchQueue.global().asyncAfter(deadline: .now() + 30) {
                gate.finish(continuation, result: .failure(SelfTestError.failed("Speech transcription timed out.")))
            }
        }
    }

    private static func speechAuthorizationLabel(_ status: SFSpeechRecognizerAuthorizationStatus) -> String {
        switch status {
        case .authorized:
            return "authorized"
        case .denied:
            return "denied"
        case .notDetermined:
            return "not_determined"
        case .restricted:
            return "restricted"
        @unknown default:
            return "unknown"
        }
    }
    #endif
}

#if canImport(Speech)
private struct SpeechAuthorizationResult: Sendable {
    let status: SFSpeechRecognizerAuthorizationStatus
    let timedOut: Bool
}

private final class SpeechAuthorizationGate: @unchecked Sendable {
    private let lock = NSLock()
    private var finished = false

    func finish(
        _ continuation: CheckedContinuation<SpeechAuthorizationResult, Never>,
        result: SpeechAuthorizationResult
    ) {
        lock.lock()
        if finished {
            lock.unlock()
            return
        }
        finished = true
        lock.unlock()
        continuation.resume(returning: result)
    }
}

private final class SpeechTranscriptionGate: @unchecked Sendable {
    private let lock = NSLock()
    private var task: SFSpeechRecognitionTask?
    private var finished = false

    func setTask(_ task: SFSpeechRecognitionTask?) {
        lock.lock()
        defer {
            lock.unlock()
        }
        self.task = task
    }

    func finish(_ continuation: CheckedContinuation<String, Error>, result: Result<String, Error>) {
        let taskToCancel: SFSpeechRecognitionTask?
        lock.lock()
        if finished {
            lock.unlock()
            return
        }
        finished = true
        taskToCancel = task
        task = nil
        lock.unlock()

        taskToCancel?.cancel()
        switch result {
        case .success(let transcript):
            continuation.resume(returning: transcript)
        case .failure(let error):
            continuation.resume(throwing: error)
        }
    }
}
#endif

enum SelfTestError: Error, CustomStringConvertible {
    case failed(String)

    var description: String {
        switch self {
        case .failed(let message):
            return message
        }
    }
}
