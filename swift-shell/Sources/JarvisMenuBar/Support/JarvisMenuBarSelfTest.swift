import Foundation
import JarvisClient

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
            throw SelfTestError.failed("Generic email requests should use worker mail routes before native OCR.")
        }
        guard JarvisShellModel.shouldUseWorkerMailRead("check my email and summarize the newest email in my inbox") else {
            throw SelfTestError.failed("Generic email requests should use the structured worker mail route.")
        }
        guard JarvisShellModel.shouldUseNativeOutlookRead("read the visible Outlook screen with OCR") else {
            throw SelfTestError.failed("Explicit visible Outlook OCR requests should use native OCR.")
        }
        guard !JarvisShellModel.shouldUseWorkerMailRead("read the visible Outlook screen with OCR") else {
            throw SelfTestError.failed("Explicit visible OCR requests should not use the generic mail route first.")
        }
        guard !JarvisShellModel.shouldUseNativeOutlookRead("send an email with a screenshot") else {
            throw SelfTestError.failed("Blocked email actions must not use native read routing.")
        }
        guard !JarvisShellModel.shouldUseWorkerMailRead("send an email with a screenshot") else {
            throw SelfTestError.failed("Blocked email actions must not use worker read routing.")
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
        guard JarvisShellModel.shouldUseNativeTTSStatus("tts status") else {
            throw SelfTestError.failed("TTS status should use the native Swift TTS snapshot.")
        }
        guard JarvisShellModel.shouldUseNativeTTSStatus("can you speak") else {
            throw SelfTestError.failed("Natural TTS readiness questions should use the native Swift TTS snapshot.")
        }
        guard !JarvisShellModel.shouldUseNativeTTSStatus("say out loud hello") else {
            throw SelfTestError.failed("Actual speech commands must not be treated as read-only TTS status.")
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
        guard summary.contains("/\(expectedIds.count) permissions ready") else {
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
}

enum SelfTestError: Error, CustomStringConvertible {
    case failed(String)

    var description: String {
        switch self {
        case .failed(let message):
            return message
        }
    }
}
