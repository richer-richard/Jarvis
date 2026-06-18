import AppKit
import Foundation

public struct NativeBrowserPageReadResult: Sendable {
    public let browser: String
    public let status: String
    public let title: String
    public let url: String
    public let domain: String
    public let pageText: String
    public let chromeAutomation: NativeBrowserAutomationPermissionResult
    public let returnCode: Int32
    public let stderr: String
    public let appBundlePath: String
    public let appExecutablePath: String
    public let bundleIdentifier: String

    public init(
        browser: String,
        status: String,
        title: String = "",
        url: String = "",
        domain: String = "",
        pageText: String = "",
        chromeAutomation: NativeBrowserAutomationPermissionResult,
        returnCode: Int32 = 0,
        stderr: String = "",
        appBundlePath: String = Bundle.main.bundleURL.path,
        appExecutablePath: String = Bundle.main.executableURL?.path ?? "",
        bundleIdentifier: String = Bundle.main.bundleIdentifier ?? ""
    ) {
        self.browser = browser
        self.status = status
        self.title = title
        self.url = url
        self.domain = domain
        self.pageText = pageText
        self.chromeAutomation = chromeAutomation
        self.returnCode = returnCode
        self.stderr = stderr
        self.appBundlePath = appBundlePath
        self.appExecutablePath = appExecutablePath
        self.bundleIdentifier = bundleIdentifier
    }

    public var jsonObject: [String: Any] {
        [
            "browser": browser,
            "status": status,
            "title": title,
            "url": url,
            "domain": domain,
            "page_text": pageText,
            "chrome_automation": chromeAutomation.jsonObject,
            "returncode": returnCode,
            "stderr": stderr,
            "app_bundle_path": appBundlePath,
            "app_executable_path": appExecutablePath,
            "bundle_identifier": bundleIdentifier,
        ]
    }
}

public enum JarvisNativeBrowserReader {
    public static let fieldDelimiter = "::jarvis-browser-field::"

    public static func readChromeActiveTab(
        includePageText: Bool = false,
        textLimit: Int = 6000
    ) -> NativeBrowserPageReadResult {
        let permission = JarvisNativeBrowserPermission.chromeAutomationStatus()
        return readChromeActiveTab(
            includePageText: includePageText,
            textLimit: textLimit,
            permission: permission
        )
    }

    private static func readChromeActiveTab(
        includePageText: Bool,
        textLimit: Int,
        permission: NativeBrowserAutomationPermissionResult
    ) -> NativeBrowserPageReadResult {
        let boundedLimit = max(1, min(textLimit, 6001))
        guard let script = NSAppleScript(source: chromeReadScript(includePageText: includePageText, textLimit: boundedLimit)) else {
            return NativeBrowserPageReadResult(
                browser: "Google Chrome",
                status: "script_unavailable",
                chromeAutomation: permission,
                returnCode: 1,
                stderr: "Could not prepare the Chrome AppleScript."
            )
        }

        var errorInfo: NSDictionary?
        let descriptor = script.executeAndReturnError(&errorInfo)
        if let errorInfo {
            return errorResult(
                errorInfo: errorInfo,
                includePageText: includePageText,
                textLimit: boundedLimit,
                permission: permission
            )
        }

        let output = descriptor.stringValue ?? ""
        let fields = output.components(separatedBy: fieldDelimiter)
        let status = fields.first?.trimmingCharacters(in: .whitespacesAndNewlines) ?? "unknown"
        if status != "checked" {
            return NativeBrowserPageReadResult(
                browser: "Google Chrome",
                status: status.isEmpty ? "unknown" : status,
                chromeAutomation: permission
            )
        }

        let title = fields.count > 1 ? fields[1].trimmingCharacters(in: .whitespacesAndNewlines) : ""
        let url = fields.count > 2 ? fields[2].trimmingCharacters(in: .whitespacesAndNewlines) : ""
        let pageText = includePageText && fields.count > 3 ? fields[3] : ""
        return NativeBrowserPageReadResult(
            browser: "Google Chrome",
            status: "checked",
            title: title,
            url: url,
            domain: safeDomain(for: url),
            pageText: pageText,
            chromeAutomation: permission
        )
    }

    private static func errorResult(
        errorInfo: NSDictionary,
        includePageText: Bool,
        textLimit: Int,
        permission: NativeBrowserAutomationPermissionResult
    ) -> NativeBrowserPageReadResult {
        let number = Int32((errorInfo[NSAppleScript.errorNumber] as? NSNumber)?.intValue ?? 1)
        let message = String(describing: errorInfo[NSAppleScript.errorMessage] ?? "AppleScript execution failed.")
        let lowerMessage = message.lowercased()

        var status = "automation_error"
        if number == -1743 || number == -1723
            || lowerMessage.contains("not allowed")
            || lowerMessage.contains("not authorized")
            || lowerMessage.contains("not permitted")
            || lowerMessage.contains("access not allowed") {
            status = "automation_not_allowed"
        } else if includePageText
            && (lowerMessage.contains("javascript") || lowerMessage.contains("apple events")) {
            status = "chrome_javascript_unavailable"
        }

        if includePageText && status == "chrome_javascript_unavailable" {
            let fallback = readChromeActiveTab(
                includePageText: false,
                textLimit: textLimit,
                permission: permission
            )
            let fallbackStatus = browserIsTeamsTarget(url: fallback.url, title: fallback.title)
                ? "teams_page_text_unavailable"
                : status
            return NativeBrowserPageReadResult(
                browser: fallback.browser,
                status: fallbackStatus,
                title: fallback.title,
                url: fallback.url,
                domain: fallback.domain,
                pageText: "",
                chromeAutomation: permission,
                returnCode: number,
                stderr: message
            )
        }

        let effectivePermission = status == "automation_not_allowed"
            ? blockedAutomationPermission(from: permission, code: number)
            : permission
        return NativeBrowserPageReadResult(
            browser: "Google Chrome",
            status: status,
            chromeAutomation: effectivePermission,
            returnCode: number,
            stderr: message
        )
    }

    private static func chromeReadScript(includePageText: Bool, textLimit: Int) -> String {
        let javascript = [
            "(() => { ",
            "const body = document.body; ",
            "const text = body ? body.innerText : ''; ",
            "return String(text || '').replace(/[\\\\t\\\\r]+/g, ' ').slice(0, ",
            "\(textLimit)",
            "); ",
            "})()",
        ].joined()
        let pageScript: String
        let returnFields: String
        if includePageText {
            pageScript = "\n    set pageText to execute javascript \"\(escapeAppleScriptString(javascript))\" in theTab"
            returnFields = "theStatus & d & theTitle & d & theURL & d & pageText"
        } else {
            pageScript = ""
            returnFields = "theStatus & d & theTitle & d & theURL"
        }
        return """
set d to "\(escapeAppleScriptString(fieldDelimiter))"
if application "Google Chrome" is not running then
    return "not_running" & d & "" & d & ""
end if
tell application "Google Chrome"
    if (count of windows) = 0 then
        return "no_window" & d & "" & d & ""
    end if
    set theTab to active tab of front window
    set theStatus to "checked"
    set theTitle to title of theTab
    set theURL to URL of theTab\(pageScript)
    return \(returnFields)
end tell
"""
    }

    private static func safeDomain(for url: String) -> String {
        guard let host = URL(string: url)?.host else {
            return ""
        }
        return String(host.prefix(120))
    }

    private static func browserIsTeamsTarget(url: String, title: String) -> Bool {
        let domain = safeDomain(for: url).lowercased()
        let normalizedTitle = title.folding(options: [.caseInsensitive], locale: .current)
        return domain == "teams.microsoft.com"
            || domain.hasSuffix(".teams.microsoft.com")
            || domain == "teams.cloud.microsoft"
            || domain.hasSuffix(".teams.cloud.microsoft")
            || normalizedTitle.contains("microsoft teams")
    }

    private static func blockedAutomationPermission(
        from original: NativeBrowserAutomationPermissionResult,
        code: Int32
    ) -> NativeBrowserAutomationPermissionResult {
        NativeBrowserAutomationPermissionResult(
            browser: original.browser,
            targetBundleIdentifier: original.targetBundleIdentifier,
            status: "needs_automation_access",
            stateLabel: "Needs Automation Access",
            detail: "Grant Jarvis under Privacy & Security > Automation > \(original.browser), and enable \(original.browser)'s Allow JavaScript from Apple Events setting.",
            isReady: false,
            requiresUserAction: true,
            permissionCode: code,
            appBundlePath: original.appBundlePath,
            appExecutablePath: original.appExecutablePath,
            bundleIdentifier: original.bundleIdentifier
        )
    }

    private static func escapeAppleScriptString(_ value: String) -> String {
        value
            .replacingOccurrences(of: "\\", with: "\\\\")
            .replacingOccurrences(of: "\"", with: "\\\"")
    }
}
