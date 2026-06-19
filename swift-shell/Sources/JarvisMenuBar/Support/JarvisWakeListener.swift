@preconcurrency import AVFoundation
import Foundation
#if canImport(Speech)
@preconcurrency import Speech
#endif

#if canImport(Speech)
private final class JarvisWakeAudioTapSink: @unchecked Sendable {
    private let request: SFSpeechAudioBufferRecognitionRequest

    init(request: SFSpeechAudioBufferRecognitionRequest) {
        self.request = request
    }

    func append(_ buffer: AVAudioPCMBuffer) {
        request.append(buffer)
    }
}

private func installJarvisWakeAudioTap(
    on input: AVAudioInputNode,
    request: SFSpeechAudioBufferRecognitionRequest
) {
    let format = input.outputFormat(forBus: 0)
    let sink = JarvisWakeAudioTapSink(request: request)
    input.installTap(onBus: 0, bufferSize: 1024, format: format) { [sink] buffer, _ in
        sink.append(buffer)
    }
}
#endif

struct JarvisWakeListenerSnapshot: Equatable {
    let running: Bool
    let phase: String
    let status: String
    let transcript: String
    let engine: String
}

@MainActor
final class JarvisWakeListener {
    private static let wakeSimilarityThreshold = 0.86
    private static let restartStormLimit = 2
    private static let restartStormWindowSeconds: TimeInterval = 24
    private static let minimumStableRecognitionSeconds: TimeInterval = 8
    private static let wakeRestartDelaySeconds: TimeInterval = 2.5
    private static let commandRestartDelaySeconds: TimeInterval = 1.2
    private static let postCommandRestartDelaySeconds: TimeInterval = 4.0
    private static let recoveryRestartDelaySeconds: TimeInterval = 5.0

    var onStateChange: ((JarvisWakeListenerSnapshot) -> Void)?
    var onWakeDetected: ((String) -> Void)?
    var onCommandCaptured: ((String, String) -> Void)?
    var onCommandIgnored: ((String, String, String) -> Void)?

    private enum Phase {
        case stopped
        case waitingForWake
        case awaitingCommand
        case restarting

        var label: String {
            switch self {
            case .stopped:
                return "Off"
            case .waitingForWake:
                return "Listening"
            case .awaitingCommand:
                return "Awake"
            case .restarting:
                return "Resetting"
            }
        }
    }

    private var phase: Phase = .stopped
    private var status: String = "Wake listener off"
    private var lastTranscript: String = ""
    private var engineLabel: String = "Apple Speech"
    private var shouldKeepRunning = false
    private var restartTask: Task<Void, Never>?
    private var captureTask: Task<Void, Never>?
    private var pendingCommand: String = ""
    private var recognitionGeneration = 0
    private var recentRestartTimes: [Date] = []
    private var restartAttemptsSinceActivation = 0
    private var currentRecognitionStartedAt: Date?
    private var currentSessionHeardTranscript = false
    private var lastPublishedSnapshot: JarvisWakeListenerSnapshot?

    #if canImport(Speech)
    private let recognizer = SFSpeechRecognizer(locale: Locale(identifier: "en-US"))
    private var audioEngine: AVAudioEngine?
    private var recognitionRequest: SFSpeechAudioBufferRecognitionRequest?
    private var recognitionTask: SFSpeechRecognitionTask?
    #endif

    var snapshot: JarvisWakeListenerSnapshot {
        JarvisWakeListenerSnapshot(
            running: shouldKeepRunning,
            phase: phase.label,
            status: status,
            transcript: lastTranscript,
            engine: engineLabel
        )
    }

    func start() {
        #if canImport(Speech)
        guard recognizer != nil else {
            status = "Speech recognizer unavailable"
            phase = .stopped
            shouldKeepRunning = false
            publish()
            return
        }
        shouldKeepRunning = true
        recentRestartTimes = []
        restartAttemptsSinceActivation = 0
        status = "Requesting microphone and speech access"
        phase = .restarting
        publish()
        Task { @MainActor in
            let authorized = await Self.requestPermissions()
            guard authorized else {
                self.shouldKeepRunning = false
                self.phase = .stopped
                self.status = "Microphone or Speech Recognition permission is missing"
                self.publish()
                return
            }
            self.phase = .waitingForWake
            self.status = "Listening for Hey Jarvis"
            self.publish()
            self.startRecognitionSession()
        }
        #else
        status = "Speech framework unavailable in this build"
        phase = .stopped
        shouldKeepRunning = false
        publish()
        #endif
    }

    func stop() {
        shouldKeepRunning = false
        restartTask?.cancel()
        restartTask = nil
        captureTask?.cancel()
        captureTask = nil
        pendingCommand = ""
        recentRestartTimes = []
        stopRecognitionSession()
        phase = .stopped
        status = "Wake listener off"
        publish()
    }

    #if canImport(Speech)
    nonisolated private static func requestPermissions() async -> Bool {
        guard hasRequiredVoiceUsageDescriptions() else {
            return false
        }
        if isRunningWakeSelfTestWithoutTCC() {
            return true
        }
        let micAllowed = await withCheckedContinuation { continuation in
            AVCaptureDevice.requestAccess(for: .audio) { granted in
                continuation.resume(returning: granted)
            }
        }
        guard micAllowed else {
            return false
        }
        let speechAllowed = await withCheckedContinuation { continuation in
            SFSpeechRecognizer.requestAuthorization { status in
                continuation.resume(returning: status == .authorized)
            }
        }
        return speechAllowed
    }

    nonisolated private static func hasRequiredVoiceUsageDescriptions(
        bundle: Bundle = .main
    ) -> Bool {
        let microphoneUsage = bundle.object(forInfoDictionaryKey: "NSMicrophoneUsageDescription") as? String
        let speechUsage = bundle.object(forInfoDictionaryKey: "NSSpeechRecognitionUsageDescription") as? String
        return microphoneUsage?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false
            && speechUsage?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false
    }

    nonisolated private static func isRunningWakeSelfTestWithoutTCC() -> Bool {
        let arguments = CommandLine.arguments
        return arguments.contains("--wake-permission-self-test")
            || arguments.contains("--wake-start-self-test")
            || arguments.contains("--wake-soak-self-test")
    }

    static func testHasRequiredVoiceUsageDescriptions() -> Bool {
        hasRequiredVoiceUsageDescriptions()
    }

    private func startRecognitionSession() {
        guard shouldKeepRunning, let recognizer else {
            return
        }
        stopRecognitionSession()
        recognitionGeneration += 1
        let generation = recognitionGeneration
        guard recognizer.isAvailable else {
            recoverAfterRecognitionIssue(status: "Speech Recognition is not available; keeping Hey Jarvis active")
            return
        }

        let request = SFSpeechAudioBufferRecognitionRequest()
        request.shouldReportPartialResults = true
        if #available(macOS 13.0, *), recognizer.supportsOnDeviceRecognition {
            request.requiresOnDeviceRecognition = true
            engineLabel = "Apple Speech on-device"
        } else {
            engineLabel = "Apple Speech"
        }

        let engine = AVAudioEngine()
        let input = engine.inputNode
        installJarvisWakeAudioTap(on: input, request: request)
        engine.prepare()

        recognitionRequest = request
        audioEngine = engine
        currentRecognitionStartedAt = Date()
        currentSessionHeardTranscript = false
        do {
            try engine.start()
        } catch {
            recoverAfterRecognitionIssue(status: "Microphone engine failed; restarting Hey Jarvis: \(error.localizedDescription)")
            return
        }

        recognitionTask = Self.makeRecognitionTask(listener: self, recognizer: recognizer, request: request, generation: generation)
        status = phase == .awaitingCommand ? "Listening for your command" : "Listening for Hey Jarvis"
        publish()
    }

    nonisolated private static func makeRecognitionTask(
        listener: JarvisWakeListener,
        recognizer: SFSpeechRecognizer,
        request: SFSpeechAudioBufferRecognitionRequest,
        generation: Int
    ) -> SFSpeechRecognitionTask {
        recognizer.recognitionTask(with: request) { [weak listener] result, error in
            let transcript = result?.bestTranscription.formattedString
            let isFinal = result?.isFinal == true
            let hasError = error != nil
            Task { @MainActor [weak listener, transcript, isFinal, hasError, generation] in
                listener?.handleRecognition(transcript: transcript, isFinal: isFinal, hasError: hasError, generation: generation)
            }
        }
    }

    private func stopRecognitionSession() {
        recognitionGeneration += 1
        captureTask?.cancel()
        captureTask = nil
        recognitionTask?.cancel()
        recognitionTask = nil
        recognitionRequest?.endAudio()
        recognitionRequest = nil
        if let audioEngine {
            audioEngine.inputNode.removeTap(onBus: 0)
            audioEngine.stop()
        }
        audioEngine = nil
        currentRecognitionStartedAt = nil
        currentSessionHeardTranscript = false
    }

    private func handleRecognition(transcript: String?, isFinal: Bool, hasError: Bool, generation: Int) {
        guard generation == recognitionGeneration else {
            return
        }
        if let transcript, !transcript.isEmpty {
            currentSessionHeardTranscript = true
            lastTranscript = transcript
            switch phase {
            case .waitingForWake:
                handleWakeCandidate(lastTranscript)
            case .awaitingCommand:
                handleCommandCandidate(lastTranscript)
            case .stopped, .restarting:
                break
            }
            publish()
        }
        if hasError || isFinal {
            guard shouldKeepRunning else {
                return
            }
            let sessionAge = Date().timeIntervalSince(currentRecognitionStartedAt ?? Date())
            if Self.shouldPauseAfterSilentRecognitionEnd(
                heardTranscript: currentSessionHeardTranscript,
                sessionAge: sessionAge,
                phase: phase
            ) {
                recoverAfterRecognitionIssue(
                    status: "Speech Recognition ended before hearing speech; restarting Hey Jarvis",
                    delay: phase == .awaitingCommand ? Self.commandRestartDelaySeconds : Self.wakeRestartDelaySeconds
                )
                return
            }
            let restartDelay = phase == .awaitingCommand ? Self.commandRestartDelaySeconds : Self.wakeRestartDelaySeconds
            stopRecognitionSession()
            scheduleRestart(after: restartDelay)
        }
    }

    private func handleWakeCandidate(_ transcript: String) {
        let detection = Self.detectWake(transcript)
        guard detection.detected else {
            return
        }
        if !detection.command.isEmpty {
            status = "Wake detected"
            captureCommand(detection.command, transcript: transcript)
            return
        }
        phase = .awaitingCommand
        pendingCommand = ""
        captureTask?.cancel()
        status = "Wake detected; listening for your command"
        onWakeDetected?(transcript)
    }

    private func handleCommandCandidate(_ transcript: String) {
        var command = Self.normalized(transcript)
        let wake = Self.detectWake(transcript)
        if wake.detected {
            guard !wake.command.isEmpty else {
                onCommandIgnored?("repeated_wake", transcript, "")
                return
            }
            command = wake.command
        }
        guard !Self.isWakeGreetingEcho(command) else {
            onCommandIgnored?("wake_greeting_echo", transcript, command)
            return
        }
        guard command.count >= 2 else {
            return
        }
        pendingCommand = command
        status = "Command heard"
        captureTask?.cancel()
        captureTask = Task { @MainActor [weak self, command, transcript] in
            try? await Task.sleep(nanoseconds: 950_000_000)
            guard let self, self.phase == .awaitingCommand, self.pendingCommand == command else {
                return
            }
            self.captureCommand(command, transcript: transcript)
        }
    }

    private func captureCommand(_ command: String, transcript: String) {
        let cleanedCommand = Self.cleanCommand(command)
        guard !cleanedCommand.isEmpty else {
            return
        }
        captureTask?.cancel()
        captureTask = nil
        pendingCommand = ""
        status = "Command captured"
        phase = .restarting
        currentSessionHeardTranscript = true
        stopRecognitionSession()
        publish()
        onCommandCaptured?(cleanedCommand, transcript)
        if shouldKeepRunning {
            phase = .waitingForWake
            scheduleRestart(after: Self.postCommandRestartDelaySeconds, countsTowardStability: false)
        }
    }

    private func scheduleRestart(
        after seconds: TimeInterval,
        generation: Int? = nil,
        countsTowardStability: Bool = true
    ) {
        restartTask?.cancel()
        guard shouldKeepRunning else {
            return
        }
        if let generation, generation != recognitionGeneration {
            return
        }
        var restartDelay = seconds
        if countsTowardStability {
            restartAttemptsSinceActivation += 1
            let decision = Self.restartStormDecision(priorRestartTimes: recentRestartTimes, now: Date())
            recentRestartTimes = decision.restartTimes
            if decision.shouldPause {
                restartDelay = max(restartDelay, Self.recoveryRestartDelaySeconds)
                status = "Speech Recognition is recovering; Hey Jarvis is still listening"
            }
        }
        phase = phase == .awaitingCommand ? .awaitingCommand : .restarting
        publish()
        restartTask = Task { @MainActor [weak self, generation] in
            let nanoseconds = UInt64(max(0.05, restartDelay) * 1_000_000_000)
            try? await Task.sleep(nanoseconds: nanoseconds)
            guard let self, self.shouldKeepRunning else {
                return
            }
            if let generation, generation != self.recognitionGeneration {
                return
            }
            if self.phase == .restarting {
                self.phase = .waitingForWake
            }
            self.startRecognitionSession()
        }
    }

    private func recoverAfterRecognitionIssue(status: String, delay: TimeInterval? = nil) {
        guard shouldKeepRunning else {
            return
        }
        restartTask?.cancel()
        restartTask = nil
        captureTask?.cancel()
        captureTask = nil
        pendingCommand = ""
        stopRecognitionSession()
        phase = .restarting
        self.status = status
        publish()
        scheduleRestart(after: delay ?? Self.recoveryRestartDelaySeconds, countsTowardStability: false)
    }
    #else
    private func stopRecognitionSession() {}
    #endif

    private func publish() {
        let currentSnapshot = snapshot
        guard currentSnapshot != lastPublishedSnapshot else {
            return
        }
        lastPublishedSnapshot = currentSnapshot
        onStateChange?(currentSnapshot)
    }

    private struct Detection {
        let detected: Bool
        let phrase: String?
        let command: String
        let score: Double
        let threshold: Double
        let window: String
        let normalized: String
        let startWordIndex: Int?
        let mode: String

        var diagnostics: [String: String] {
            var fields: [String: String] = [
                "detected": detected ? "true" : "false",
                "command": command,
                "score": String(format: "%.6f", score),
                "threshold": String(format: "%.2f", threshold),
                "window": window,
                "normalized": normalized,
                "mode": mode,
            ]
            if let phrase {
                fields["phrase"] = phrase
            }
            if let startWordIndex {
                fields["start_word_index"] = String(startWordIndex)
            }
            return fields
        }
    }

    static func testDetectWake(_ transcript: String) -> (detected: Bool, command: String) {
        let detection = detectWake(transcript)
        return (detection.detected, detection.command)
    }

    static func testWakeScore(_ transcript: String) -> [String: String] {
        detectWake(transcript).diagnostics
    }

    static func testCleanCommand(_ command: String) -> String {
        cleanCommand(command)
    }

    static func testRestartStormDecision(priorRestartAges: [TimeInterval], now: Date) -> (count: Int, shouldPause: Bool) {
        let priorRestartTimes = priorRestartAges.map { now.addingTimeInterval(-$0) }
        let decision = restartStormDecision(priorRestartTimes: priorRestartTimes, now: now)
        return (decision.restartTimes.count, decision.shouldPause)
    }

    static func testRestartDelaySeconds(awaitingCommand: Bool, afterCommandCapture: Bool = false) -> TimeInterval {
        if afterCommandCapture {
            return postCommandRestartDelaySeconds
        }
        return awaitingCommand ? commandRestartDelaySeconds : wakeRestartDelaySeconds
    }

    static func testActivationRestartLimit(priorAttempts: Int) -> (attempts: Int, shouldPause: Bool) {
        let attempts = max(0, priorAttempts) + 1
        return (attempts, shouldPauseAfterActivationRestartLimit(restartAttempts: attempts))
    }

    func testDuplicatePublishCount() -> Int {
        var count = 0
        let previousHandler = onStateChange
        onStateChange = { _ in
            count += 1
        }
        publish()
        publish()
        onStateChange = previousHandler
        return count
    }

    static func testSilentEndDecision(
        sessionAgeSeconds: TimeInterval,
        heardTranscript: Bool,
        awaitingCommand: Bool = false
    ) -> Bool {
        shouldPauseAfterSilentRecognitionEnd(
            heardTranscript: heardTranscript,
            sessionAge: sessionAgeSeconds,
            phase: awaitingCommand ? .awaitingCommand : .waitingForWake
        )
    }

    #if canImport(Speech)
    static func testPermissionCallbackPath() async -> Bool {
        await requestPermissions()
    }

    static func testVoiceUsageDescriptionPreflight() -> Bool {
        testHasRequiredVoiceUsageDescriptions()
    }
    #else
    static func testPermissionCallbackPath() async -> Bool {
        false
    }

    static func testVoiceUsageDescriptionPreflight() -> Bool {
        false
    }
    #endif

    private static func restartStormDecision(
        priorRestartTimes: [Date],
        now: Date
    ) -> (restartTimes: [Date], shouldPause: Bool) {
        let recent = (priorRestartTimes + [now]).filter {
            now.timeIntervalSince($0) <= restartStormWindowSeconds
        }
        return (recent, recent.count > restartStormLimit)
    }

    private static func shouldPauseAfterSilentRecognitionEnd(
        heardTranscript: Bool,
        sessionAge: TimeInterval,
        phase: Phase
    ) -> Bool {
        (phase == .waitingForWake || phase == .awaitingCommand)
            && !heardTranscript
            && sessionAge < minimumStableRecognitionSeconds
    }

    private static func shouldPauseAfterActivationRestartLimit(restartAttempts: Int) -> Bool {
        false
    }

    private static func detectWake(_ transcript: String) -> Detection {
        let normalizedText = normalized(transcript)
        let phrases = ["hey jarvis", "okay jarvis", "ok jarvis"]
        for phrase in phrases {
            if normalizedText == phrase {
                return Detection(
                    detected: true,
                    phrase: phrase,
                    command: "",
                    score: 1,
                    threshold: wakeSimilarityThreshold,
                    window: phrase,
                    normalized: normalizedText,
                    startWordIndex: 0,
                    mode: "exact_prefix"
                )
            }
            let prefix = phrase + " "
            if normalizedText.hasPrefix(prefix) {
                return Detection(
                    detected: true,
                    phrase: phrase,
                    command: cleanCommand(String(normalizedText.dropFirst(prefix.count))),
                    score: 1,
                    threshold: wakeSimilarityThreshold,
                    window: phrase,
                    normalized: normalizedText,
                    startWordIndex: 0,
                    mode: "exact_prefix"
                )
            }
        }
        guard let best = bestFuzzyWakeMatch(normalizedText) else {
            return Detection(
                detected: false,
                phrase: nil,
                command: "",
                score: 0,
                threshold: wakeSimilarityThreshold,
                window: "",
                normalized: normalizedText,
                startWordIndex: nil,
                mode: "fuzzy_window"
            )
        }
        guard best.score >= wakeSimilarityThreshold else {
            return Detection(
                detected: false,
                phrase: nil,
                command: "",
                score: best.score,
                threshold: wakeSimilarityThreshold,
                window: best.window,
                normalized: normalizedText,
                startWordIndex: best.startWordIndex,
                mode: "fuzzy_window"
            )
        }
        return Detection(
            detected: true,
            phrase: best.phrase,
            command: cleanCommand(best.command),
            score: best.score,
            threshold: wakeSimilarityThreshold,
            window: best.window,
            normalized: normalizedText,
            startWordIndex: best.startWordIndex,
            mode: "fuzzy_window"
        )
    }

    private static func bestFuzzyWakeMatch(_ normalizedText: String) -> (
        phrase: String,
        score: Double,
        window: String,
        startWordIndex: Int,
        command: String
    )? {
        let words = normalizedText.split(separator: " ").map(String.init)
        let phrases = ["hey jarvis", "okay jarvis", "ok jarvis"]
        var best: (phrase: String, score: Double, window: String, startWordIndex: Int, command: String)?
        for phrase in phrases {
            let phraseWords = phrase.split(separator: " ").map(String.init)
            guard !phraseWords.isEmpty, words.count >= phraseWords.count else {
                continue
            }
            for index in 0...(words.count - phraseWords.count) {
                let windowWords = Array(words[index..<(index + phraseWords.count)])
                let score = phraseSimilarityWords(windowWords, phraseWords)
                if best == nil || score > (best?.score ?? 0) {
                    best = (
                        phrase: phrase,
                        score: score,
                        window: windowWords.joined(separator: " "),
                        startWordIndex: index,
                        command: words.dropFirst(index + phraseWords.count).joined(separator: " ")
                    )
                }
            }
        }
        return best
    }

    private static func normalized(_ value: String) -> String {
        value
            .lowercased()
            .replacingOccurrences(of: #"[^a-z0-9]+"#, with: " ", options: .regularExpression)
            .split(separator: " ")
            .joined(separator: " ")
    }

    private static func cleanCommand(_ value: String) -> String {
        normalized(value)
            .replacingOccurrences(of: #"^(yes\s+sir\s+)+"#, with: "", options: .regularExpression)
            .replacingOccurrences(of: #"^yes\s+"#, with: "", options: .regularExpression)
            .replacingOccurrences(of: #"^(please\s+)+"#, with: "", options: .regularExpression)
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private static func isWakeGreetingEcho(_ value: String) -> Bool {
        ["yes", "yes sir", "yes sir yes sir"].contains(normalized(value))
    }

    private static func phraseSimilarity(_ left: String, _ right: String) -> Double {
        let leftWords = left.split(separator: " ").map(String.init)
        let rightWords = right.split(separator: " ").map(String.init)
        return phraseSimilarityWords(leftWords, rightWords)
    }

    private static func phraseSimilarityWords(_ leftWords: [String], _ rightWords: [String]) -> Double {
        guard leftWords.count == rightWords.count, !leftWords.isEmpty else {
            return 0
        }
        let scores = zip(leftWords, rightWords).map { wordSimilarity($0.0, $0.1) }
        return scores.reduce(0, +) / Double(scores.count)
    }

    private static func wordSimilarity(_ left: String, _ right: String) -> Double {
        if left == right {
            return 1
        }
        let distance = levenshtein(left, right)
        return max(0, 1 - Double(distance) / Double(max(left.count, right.count, 1)))
    }

    private static func levenshtein(_ left: String, _ right: String) -> Int {
        let leftChars = Array(left)
        let rightChars = Array(right)
        var previous = Array(0...rightChars.count)
        for (row, leftChar) in leftChars.enumerated() {
            var current = [row + 1]
            for (column, rightChar) in rightChars.enumerated() {
                let cost = leftChar == rightChar ? 0 : 1
                current.append(
                    min(
                        previous[column + 1] + 1,
                        current[column] + 1,
                        previous[column] + cost
                    )
                )
            }
            previous = current
        }
        return previous.last ?? 0
    }
}
