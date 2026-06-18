import ApplicationServices
import AVFoundation
import CoreGraphics
import Foundation
import JarvisMacNative
#if canImport(Speech)
import Speech
#endif
import UserNotifications

enum JarvisPermissionService {
    static func snapshot() async -> [PermissionReadiness] {
        var permissions = [
            microphoneStatus(),
            speechRecognitionStatus(),
            screenRecordingStatus(),
            accessibilityStatus(),
            calendarCacheStatus(),
            chromeAutomationStatus(),
        ]
        permissions.append(await notificationStatus())
        return permissions
    }

    static func summary(_ permissions: [PermissionReadiness]) -> String {
        let readyCount = permissions.filter(\.isReady).count
        return "App perms: \(readyCount)/\(permissions.count) ready"
    }

    static func wakeStartPreflight() -> WakeStartPreflight {
        wakeStartPreflight(microphone: microphoneStatus(), speechRecognition: speechRecognitionStatus())
    }

    static func chromeAutomationReadiness() -> PermissionReadiness {
        chromeAutomationStatus()
    }

    static func chromeAutomationRequiresManualGrant() -> Bool {
        chromeAutomationReadiness().state == "Needs Automation Access"
    }

    static func wakeStartPreflight(
        microphone: PermissionReadiness,
        speechRecognition: PermissionReadiness
    ) -> WakeStartPreflight {
        let voicePermissions = [microphone, speechRecognition]
        let blockers = voicePermissions.filter { permission in
            !permission.isReady && !isRequestableVoiceState(permission.state)
        }
        guard !blockers.isEmpty else {
            let requestable = voicePermissions.filter { permission in
                !permission.isReady && isRequestableVoiceState(permission.state)
            }
            if !requestable.isEmpty {
                let labels = requestable.map { "\($0.label) is \($0.state.lowercased())" }.joined(separator: "; ")
                return WakeStartPreflight(
                    allowed: true,
                    message: "Hey Jarvis can start.",
                    detail: "\(labels). Starting Hey Jarvis will ask macOS for voice access if it still needs to."
                )
            }
            return WakeStartPreflight(
                allowed: true,
                message: "Hey Jarvis can start.",
                detail: "Microphone and Speech Recognition are ready."
            )
        }
        let labels = blockers.map { "\($0.label) is \($0.state.lowercased())" }.joined(separator: "; ")
        return WakeStartPreflight(
            allowed: false,
            message: "I cannot start Hey Jarvis yet. \(labels). Open Permissions and grant them first.",
            detail: labels
        )
    }

    private static func isRequestableVoiceState(_ state: String) -> Bool {
        state.caseInsensitiveCompare("Not requested") == .orderedSame
    }

    private static func microphoneStatus() -> PermissionReadiness {
        switch AVCaptureDevice.authorizationStatus(for: .audio) {
        case .authorized:
            return PermissionReadiness(
                id: "microphone",
                label: "Microphone",
                state: "Ready",
                detail: "Voice capture can be enabled later.",
                isReady: true
            )
        case .denied:
            return PermissionReadiness(
                id: "microphone",
                label: "Microphone",
                state: "Denied",
                detail: "Voice capture needs user permission in System Settings.",
                isReady: false
            )
        case .restricted:
            return PermissionReadiness(
                id: "microphone",
                label: "Microphone",
                state: "Restricted",
                detail: "Voice capture is restricted by system policy.",
                isReady: false
            )
        case .notDetermined:
            return PermissionReadiness(
                id: "microphone",
                label: "Microphone",
                state: "Not requested",
                detail: "Jarvis has not asked for microphone access.",
                isReady: false
            )
        @unknown default:
            return PermissionReadiness(
                id: "microphone",
                label: "Microphone",
                state: "Unknown",
                detail: "Unknown microphone authorization state.",
                isReady: false
            )
        }
    }

    private static func speechRecognitionStatus() -> PermissionReadiness {
        #if canImport(Speech)
        switch SFSpeechRecognizer.authorizationStatus() {
        case .authorized:
            return PermissionReadiness(
                id: "speech-recognition",
                label: "Speech Recognition",
                state: "Ready",
                detail: "Command transcription can be enabled later.",
                isReady: true
            )
        case .denied:
            return PermissionReadiness(
                id: "speech-recognition",
                label: "Speech Recognition",
                state: "Denied",
                detail: "Command transcription needs user permission in System Settings.",
                isReady: false
            )
        case .restricted:
            return PermissionReadiness(
                id: "speech-recognition",
                label: "Speech Recognition",
                state: "Restricted",
                detail: "Speech recognition is restricted by system policy.",
                isReady: false
            )
        case .notDetermined:
            return PermissionReadiness(
                id: "speech-recognition",
                label: "Speech Recognition",
                state: "Not requested",
                detail: "Jarvis has not asked for speech recognition access.",
                isReady: false
            )
        @unknown default:
            return PermissionReadiness(
                id: "speech-recognition",
                label: "Speech Recognition",
                state: "Unknown",
                detail: "Unknown speech recognition authorization state.",
                isReady: false
            )
        }
        #else
        return PermissionReadiness(
            id: "speech-recognition",
            label: "Speech Recognition",
            state: "Unavailable",
            detail: "Speech framework is not available in this build environment.",
            isReady: false
        )
        #endif
    }

    private static func screenRecordingStatus() -> PermissionReadiness {
        let ready = CGPreflightScreenCaptureAccess()
        return PermissionReadiness(
            id: "screen-recording",
            label: "Screen Recording",
            state: ready ? "Ready" : "Not granted",
            detail: ready ? "Screen inspection can be enabled later." : "Screenshot workflows need Screen Recording permission.",
            isReady: ready
        )
    }

    private static func accessibilityStatus() -> PermissionReadiness {
        let ready = AXIsProcessTrusted()
        return PermissionReadiness(
            id: "accessibility",
            label: "Accessibility",
            state: ready ? "Ready" : "Not granted",
            detail: ready ? "Desktop control can be enabled later." : "Computer-control tools need Accessibility permission.",
            isReady: ready
        )
    }

    private static func calendarCacheStatus() -> PermissionReadiness {
        let dbURL = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Group Containers/group.com.apple.calendar/Calendar.sqlitedb")
        guard FileManager.default.fileExists(atPath: dbURL.path) else {
            return PermissionReadiness(
                id: "calendar-cache",
                label: "Calendar Cache",
                state: "Missing",
                detail: "No local Calendar cache is available to read.",
                isReady: false
            )
        }
        do {
            let handle = try FileHandle(forReadingFrom: dbURL)
            try? handle.close()
            return PermissionReadiness(
                id: "calendar-cache",
                label: "Calendar Cache",
                state: "Ready",
                detail: "Schedule summaries can read the local Calendar cache.",
                isReady: true
            )
        } catch {
            return PermissionReadiness(
                id: "calendar-cache",
                label: "Calendar Cache",
                state: "Needs Full Disk Access",
                detail: "Calendar summaries need Full Disk Access for Jarvis.app, then quit and reopen Jarvis.",
                isReady: false
            )
        }
    }

    private static func chromeAutomationStatus() -> PermissionReadiness {
        let probe = JarvisNativeBrowserPermission.chromeAutomationStatus()
        return PermissionReadiness(
            id: "chrome-automation",
            label: "Chrome Automation",
            state: probe.stateLabel,
            detail: probe.detail,
            isReady: probe.isReady
        )
    }

    private static func notificationStatus() async -> PermissionReadiness {
        guard Bundle.main.bundleURL.pathExtension == "app" else {
            return PermissionReadiness(
                id: "notifications",
                label: "Notifications",
                state: "Bundle needed",
                detail: "Notification settings can be read from the packaged app bundle.",
                isReady: false
            )
        }

        return await withCheckedContinuation { continuation in
            UNUserNotificationCenter.current().getNotificationSettings { settings in
                let readiness: PermissionReadiness
                switch settings.authorizationStatus {
                case .authorized, .provisional:
                    readiness = PermissionReadiness(
                        id: "notifications",
                        label: "Notifications",
                        state: "Ready",
                        detail: "Jarvis can show user-visible prompts later.",
                        isReady: true
                    )
                case .denied:
                    readiness = PermissionReadiness(
                        id: "notifications",
                        label: "Notifications",
                        state: "Denied",
                        detail: "Approval prompts will need another visible path.",
                        isReady: false
                    )
                case .notDetermined:
                    readiness = PermissionReadiness(
                        id: "notifications",
                        label: "Notifications",
                        state: "Not requested",
                        detail: "Optional unless timers or background alerts need macOS notifications.",
                        isReady: false
                    )
                case .ephemeral:
                    readiness = PermissionReadiness(
                        id: "notifications",
                        label: "Notifications",
                        state: "Temporary",
                        detail: "Notification authorization is temporary.",
                        isReady: true
                    )
                @unknown default:
                    readiness = PermissionReadiness(
                        id: "notifications",
                        label: "Notifications",
                        state: "Unknown",
                        detail: "Unknown notification authorization state.",
                        isReady: false
                    )
                }
                continuation.resume(returning: readiness)
            }
        }
    }
}

struct PermissionReadiness: Identifiable, Equatable {
    let id: String
    let label: String
    let state: String
    let detail: String
    let isReady: Bool
}

struct WakeStartPreflight: Equatable {
    let allowed: Bool
    let message: String
    let detail: String
}
