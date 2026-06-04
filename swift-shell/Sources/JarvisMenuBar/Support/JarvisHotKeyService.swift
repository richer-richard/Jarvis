import Carbon
import Foundation

final class JarvisHotKeyService: @unchecked Sendable {
    static let defaultShortcut = HotKeyShortcut(
        keyCode: UInt32(kVK_ANSI_J),
        modifiers: UInt32(cmdKey | optionKey),
        displayName: "Command+Option+J"
    )

    private let shortcut: HotKeyShortcut
    private let onPress: @MainActor () -> Void
    private var hotKeyRef: EventHotKeyRef?
    private var eventHandlerRef: EventHandlerRef?
    private let hotKeyID = EventHotKeyID(signature: JarvisHotKeyService.fourCharCode("JARV"), id: 1)

    init(
        shortcut: HotKeyShortcut = JarvisHotKeyService.defaultShortcut,
        onPress: @escaping @MainActor () -> Void
    ) {
        self.shortcut = shortcut
        self.onPress = onPress
    }

    var displayName: String {
        shortcut.displayName
    }

    func start() -> HotKeyRegistrationResult {
        stop()

        var eventSpec = EventTypeSpec(
            eventClass: OSType(kEventClassKeyboard),
            eventKind: UInt32(kEventHotKeyPressed)
        )
        let userData = Unmanaged.passUnretained(self).toOpaque()
        let installStatus = InstallEventHandler(
            GetApplicationEventTarget(),
            JarvisHotKeyService.eventHandler,
            1,
            &eventSpec,
            userData,
            &eventHandlerRef
        )
        guard installStatus == noErr else {
            return .failed("InstallEventHandler failed: \(installStatus)")
        }

        let registerStatus = RegisterEventHotKey(
            shortcut.keyCode,
            shortcut.modifiers,
            hotKeyID,
            GetApplicationEventTarget(),
            0,
            &hotKeyRef
        )
        guard registerStatus == noErr else {
            stop()
            return .failed("RegisterEventHotKey failed: \(registerStatus)")
        }

        return .registered(shortcut.displayName)
    }

    func stop() {
        if let hotKeyRef {
            UnregisterEventHotKey(hotKeyRef)
            self.hotKeyRef = nil
        }
        if let eventHandlerRef {
            RemoveEventHandler(eventHandlerRef)
            self.eventHandlerRef = nil
        }
    }

    deinit {
        stop()
    }

    private func handlePressed(_ receivedID: EventHotKeyID) {
        guard receivedID.signature == hotKeyID.signature, receivedID.id == hotKeyID.id else {
            return
        }

        Task { @MainActor in
            onPress()
        }
    }

    private static let eventHandler: EventHandlerUPP = { _, event, userData in
        guard let event, let userData else {
            return OSStatus(eventNotHandledErr)
        }

        var receivedID = EventHotKeyID()
        let status = GetEventParameter(
            event,
            EventParamName(kEventParamDirectObject),
            EventParamType(typeEventHotKeyID),
            nil,
            MemoryLayout<EventHotKeyID>.size,
            nil,
            &receivedID
        )
        guard status == noErr else {
            return status
        }

        let service = Unmanaged<JarvisHotKeyService>
            .fromOpaque(userData)
            .takeUnretainedValue()
        service.handlePressed(receivedID)
        return noErr
    }

    private static func fourCharCode(_ value: String) -> OSType {
        var result: OSType = 0
        for byte in value.utf8.prefix(4) {
            result = (result << 8) + OSType(byte)
        }
        return result
    }
}

struct HotKeyShortcut: Equatable {
    let keyCode: UInt32
    let modifiers: UInt32
    let displayName: String
}

enum HotKeyRegistrationResult: Equatable, CustomStringConvertible {
    case registered(String)
    case failed(String)

    var isRegistered: Bool {
        switch self {
        case .registered:
            return true
        case .failed:
            return false
        }
    }

    var description: String {
        switch self {
        case .registered(let shortcut):
            return "Hotkey registered: \(shortcut)"
        case .failed(let message):
            return "Hotkey unavailable: \(message)"
        }
    }
}

