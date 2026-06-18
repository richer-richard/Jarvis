import ApplicationServices
import Foundation

public struct NativeBrowserAutomationPermissionResult: Sendable {
    public let browser: String
    public let targetBundleIdentifier: String
    public let status: String
    public let stateLabel: String
    public let detail: String
    public let isReady: Bool
    public let requiresUserAction: Bool
    public let permissionCode: Int32
    public let appBundlePath: String
    public let appExecutablePath: String
    public let bundleIdentifier: String

    public init(
        browser: String,
        targetBundleIdentifier: String,
        status: String,
        stateLabel: String,
        detail: String,
        isReady: Bool,
        requiresUserAction: Bool,
        permissionCode: Int32,
        appBundlePath: String = Bundle.main.bundleURL.path,
        appExecutablePath: String = Bundle.main.executableURL?.path ?? "",
        bundleIdentifier: String = Bundle.main.bundleIdentifier ?? ""
    ) {
        self.browser = browser
        self.targetBundleIdentifier = targetBundleIdentifier
        self.status = status
        self.stateLabel = stateLabel
        self.detail = detail
        self.isReady = isReady
        self.requiresUserAction = requiresUserAction
        self.permissionCode = permissionCode
        self.appBundlePath = appBundlePath
        self.appExecutablePath = appExecutablePath
        self.bundleIdentifier = bundleIdentifier
    }

    public var jsonObject: [String: Any] {
        [
            "browser": browser,
            "target_bundle_identifier": targetBundleIdentifier,
            "status": status,
            "state_label": stateLabel,
            "detail": detail,
            "is_ready": isReady,
            "requires_user_action": requiresUserAction,
            "permission_code": permissionCode,
            "app_bundle_path": appBundlePath,
            "app_executable_path": appExecutablePath,
            "bundle_identifier": bundleIdentifier,
        ]
    }
}

public enum JarvisNativeBrowserPermission {
    public static func chromeAutomationStatus() -> NativeBrowserAutomationPermissionResult {
        automationStatus(
            targetBundleIdentifier: "com.google.Chrome",
            browser: "Google Chrome"
        )
    }

    public static func automationStatus(
        targetBundleIdentifier: String,
        browser: String
    ) -> NativeBrowserAutomationPermissionResult {
        var target = AEAddressDesc()
        var bundleIDBytes = Array(targetBundleIdentifier.utf8)
        let createStatus = bundleIDBytes.withUnsafeMutableBytes { buffer -> OSErr in
            AECreateDesc(typeApplicationBundleID, buffer.baseAddress, buffer.count, &target)
        }
        guard createStatus == noErr else {
            return NativeBrowserAutomationPermissionResult(
                browser: browser,
                targetBundleIdentifier: targetBundleIdentifier,
                status: "unavailable",
                stateLabel: "Unavailable",
                detail: "Jarvis could not prepare the Automation permission check.",
                isReady: false,
                requiresUserAction: false,
                permissionCode: Int32(createStatus)
            )
        }
        defer {
            AEDisposeDesc(&target)
        }

        let permission = AEDeterminePermissionToAutomateTarget(
            &target,
            AEEventClass(kCoreEventClass),
            AEEventID(kAEGetData),
            false
        )
        if permission == noErr {
            return NativeBrowserAutomationPermissionResult(
                browser: browser,
                targetBundleIdentifier: targetBundleIdentifier,
                status: "preflight_ready",
                stateLabel: "Preflight Ready",
                detail: "Jarvis can ask \(browser) for Automation, but Chrome page-read access is only proven after a live read succeeds.",
                isReady: true,
                requiresUserAction: false,
                permissionCode: Int32(permission)
            )
        }
        if permission == -1744 {
            return NativeBrowserAutomationPermissionResult(
                browser: browser,
                targetBundleIdentifier: targetBundleIdentifier,
                status: "not_requested",
                stateLabel: "Not requested",
                detail: "A browser-control task can ask macOS for Automation access when needed.",
                isReady: false,
                requiresUserAction: false,
                permissionCode: Int32(permission)
            )
        }
        if permission == -1743 {
            return NativeBrowserAutomationPermissionResult(
                browser: browser,
                targetBundleIdentifier: targetBundleIdentifier,
                status: "needs_automation_access",
                stateLabel: "Needs Automation Access",
                detail: "Grant Jarvis under Privacy & Security > Automation > \(browser), and enable \(browser)'s Allow JavaScript from Apple Events setting if page control is still blocked.",
                isReady: false,
                requiresUserAction: true,
                permissionCode: Int32(permission)
            )
        }
        return NativeBrowserAutomationPermissionResult(
            browser: browser,
            targetBundleIdentifier: targetBundleIdentifier,
            status: "unknown",
            stateLabel: "Unknown",
            detail: "Automation permission returned status \(permission).",
            isReady: false,
            requiresUserAction: false,
            permissionCode: Int32(permission)
        )
    }
}
