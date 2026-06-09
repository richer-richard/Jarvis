@preconcurrency import AVFoundation
import Foundation
#if canImport(Speech)
@preconcurrency import Speech
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
        status = "Requesting microphone and speech access"
        phase = .restarting
        publish()
        Task { @MainActor in
            let authorized = await requestPermissions()
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
        stopRecognitionSession()
        phase = .stopped
        status = "Wake listener off"
        publish()
    }

    #if canImport(Speech)
    private func requestPermissions() async -> Bool {
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

    private func startRecognitionSession() {
        guard shouldKeepRunning, let recognizer else {
            return
        }
        stopRecognitionSession()
        guard recognizer.isAvailable else {
            status = "Speech recognizer is not available"
            publish()
            scheduleRestart(after: 2.0)
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
        let format = input.outputFormat(forBus: 0)
        input.installTap(onBus: 0, bufferSize: 1024, format: format) { buffer, _ in
            request.append(buffer)
        }
        engine.prepare()

        recognitionRequest = request
        audioEngine = engine
        do {
            try engine.start()
        } catch {
            status = "Microphone engine failed: \(error.localizedDescription)"
            publish()
            scheduleRestart(after: 2.0)
            return
        }

        recognitionTask = recognizer.recognitionTask(with: request) { [weak self] result, error in
            let transcript = result?.bestTranscription.formattedString
            let isFinal = result?.isFinal == true
            let hasError = error != nil
            Task { @MainActor [weak self, transcript, isFinal, hasError] in
                self?.handleRecognition(transcript: transcript, isFinal: isFinal, hasError: hasError)
            }
        }
        status = phase == .awaitingCommand ? "Listening for your command" : "Listening for Hey Jarvis"
        publish()
    }

    private func stopRecognitionSession() {
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
    }

    private func handleRecognition(transcript: String?, isFinal: Bool, hasError: Bool) {
        if let transcript, !transcript.isEmpty {
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
            scheduleRestart(after: phase == .awaitingCommand ? 0.2 : 0.7)
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
        status = "Wake detected"
        onWakeDetected?(transcript)
        scheduleRestart(after: 0.15)
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
        stopRecognitionSession()
        publish()
        onCommandCaptured?(cleanedCommand, transcript)
        if shouldKeepRunning {
            phase = .waitingForWake
            scheduleRestart(after: 3.0)
        }
    }

    private func scheduleRestart(after seconds: TimeInterval) {
        restartTask?.cancel()
        guard shouldKeepRunning else {
            return
        }
        phase = phase == .awaitingCommand ? .awaitingCommand : .restarting
        publish()
        restartTask = Task { @MainActor [weak self] in
            let nanoseconds = UInt64(max(0.05, seconds) * 1_000_000_000)
            try? await Task.sleep(nanoseconds: nanoseconds)
            guard let self, self.shouldKeepRunning else {
                return
            }
            if self.phase == .restarting {
                self.phase = .waitingForWake
            }
            self.startRecognitionSession()
        }
    }
    #else
    private func stopRecognitionSession() {}
    #endif

    private func publish() {
        onStateChange?(snapshot)
    }

    private struct Detection {
        let detected: Bool
        let command: String
    }

    static func testDetectWake(_ transcript: String) -> (detected: Bool, command: String) {
        let detection = detectWake(transcript)
        return (detection.detected, detection.command)
    }

    private static func detectWake(_ transcript: String) -> Detection {
        let normalizedText = normalized(transcript)
        let phrases = ["hey jarvis", "okay jarvis", "ok jarvis"]
        for phrase in phrases {
            if normalizedText == phrase {
                return Detection(detected: true, command: "")
            }
            let prefix = phrase + " "
            if normalizedText.hasPrefix(prefix) {
                return Detection(detected: true, command: cleanCommand(String(normalizedText.dropFirst(prefix.count))))
            }
        }
        let words = normalizedText.split(separator: " ").map(String.init)
        guard words.count >= 2 else {
            return Detection(detected: false, command: "")
        }
        for index in 0..<(words.count - 1) {
            let window = words[index] + " " + words[index + 1]
            if phraseSimilarity(window, "hey jarvis") >= 0.82 {
                let command = words.dropFirst(index + 2).joined(separator: " ")
                return Detection(detected: true, command: cleanCommand(command))
            }
        }
        return Detection(detected: false, command: "")
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
            .replacingOccurrences(of: #"^(please\s+)+"#, with: "", options: .regularExpression)
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private static func isWakeGreetingEcho(_ value: String) -> Bool {
        ["yes", "yes sir", "yes sir yes sir"].contains(normalized(value))
    }

    private static func phraseSimilarity(_ left: String, _ right: String) -> Double {
        let leftWords = left.split(separator: " ").map(String.init)
        let rightWords = right.split(separator: " ").map(String.init)
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
