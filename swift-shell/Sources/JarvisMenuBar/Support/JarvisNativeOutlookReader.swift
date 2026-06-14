import AppKit
import CoreGraphics
import Foundation
import JarvisClient
import Vision

struct NativeOutlookOCRResult: Sendable {
    let text: String
    let diagnostics: VisibleOutlookTextDiagnostics
}

enum JarvisNativeOutlookReader {
    static func readVisibleOutlookText() async throws -> NativeOutlookOCRResult {
        try await focusOutlook()
        try await Task.sleep(nanoseconds: 1_200_000_000)

        let hadAccessBeforeRequest = CGPreflightScreenCaptureAccess()
        if !hadAccessBeforeRequest {
            let granted = CGRequestScreenCaptureAccess()
            guard granted else {
                throw NativeOutlookReadError.screenRecordingDenied
            }
        }

        guard let image = captureVisibleOutlookWindow() ?? CGDisplayCreateImage(CGMainDisplayID()) else {
            throw NativeOutlookReadError.captureFailed
        }

        let lines = try recognizeText(in: image)
        let text = String(lines.joined(separator: "\n").prefix(12_000))
        return NativeOutlookOCRResult(
            text: text,
            diagnostics: VisibleOutlookTextDiagnostics(
                lineCount: lines.count,
                characterCount: text.count,
                captureWidth: image.width,
                captureHeight: image.height,
                screenAccessPreflight: hadAccessBeforeRequest,
                captureError: nil,
                appBundlePath: Bundle.main.bundleURL.path,
                appExecutablePath: Bundle.main.executableURL?.path ?? "",
                bundleIdentifier: Bundle.main.bundleIdentifier ?? ""
            )
        )
    }

    static func readVisibleScreenText(
        targetAppName: String? = nil,
        targetBundleIdentifier: String? = nil
    ) async throws -> NativeOutlookOCRResult {
        let cleanTargetName = targetAppName?.trimmingCharacters(in: .whitespacesAndNewlines)
        let cleanBundleIdentifier = targetBundleIdentifier?.trimmingCharacters(in: .whitespacesAndNewlines)
        if let cleanBundleIdentifier, !cleanBundleIdentifier.isEmpty {
            try await focusApplication(
                bundleIdentifier: cleanBundleIdentifier,
                fallbackPath: nil,
                displayName: cleanTargetName?.isEmpty == false ? cleanTargetName! : cleanBundleIdentifier
            )
            try await Task.sleep(nanoseconds: 850_000_000)
        }

        let hadAccessBeforeRequest = CGPreflightScreenCaptureAccess()
        if !hadAccessBeforeRequest {
            let granted = CGRequestScreenCaptureAccess()
            guard granted else {
                throw NativeOutlookReadError.screenRecordingDenied
            }
        }

        let ownerNames = cleanTargetName?.isEmpty == false ? Set([cleanTargetName!]) : nil
        guard let initialImage = captureVisibleWindow(ownerNames: ownerNames) ?? CGDisplayCreateImage(CGMainDisplayID()) else {
            throw NativeOutlookReadError.captureFailed
        }

        var image = initialImage
        var lines = try recognizeText(in: image)
        var source = "native_vision_ocr_screen"
        let initialText = lines.joined(separator: "\n").trimmingCharacters(in: .whitespacesAndNewlines)
        if (lines.isEmpty || lines.count <= 2 || initialText.count < 80),
           ownerNames != nil,
           let displayImage = CGDisplayCreateImage(CGMainDisplayID()) {
            let displayLines = try recognizeText(in: displayImage)
            let displayText = displayLines.joined(separator: "\n").trimmingCharacters(in: .whitespacesAndNewlines)
            if displayLines.count > lines.count || displayText.count > initialText.count + 80 {
                image = displayImage
                lines = displayLines
                source = "native_vision_ocr_screen_display_fallback"
            }
        }
        let text = String(lines.joined(separator: "\n").prefix(12_000))
        return NativeOutlookOCRResult(
            text: text,
            diagnostics: VisibleOutlookTextDiagnostics(
                source: source,
                lineCount: lines.count,
                characterCount: text.count,
                captureWidth: image.width,
                captureHeight: image.height,
                screenAccessPreflight: hadAccessBeforeRequest,
                captureError: nil,
                appBundlePath: Bundle.main.bundleURL.path,
                appExecutablePath: Bundle.main.executableURL?.path ?? "",
                bundleIdentifier: Bundle.main.bundleIdentifier ?? "",
                targetAppName: cleanTargetName ?? ""
            )
        )
    }

    @MainActor
    private static func focusOutlook() async throws {
        try await focusApplication(
            bundleIdentifier: "com.microsoft.Outlook",
            fallbackPath: "/Applications/Microsoft Outlook.app",
            displayName: "Microsoft Outlook"
        )
    }

    @MainActor
    private static func focusApplication(
        bundleIdentifier: String,
        fallbackPath: String?,
        displayName: String
    ) async throws {
        let workspace = NSWorkspace.shared
        guard let appURL = workspace.urlForApplication(withBundleIdentifier: bundleIdentifier)
            ?? fallbackPath.map({ URL(fileURLWithPath: $0) }),
              FileManager.default.fileExists(atPath: appURL.path) else {
            throw NativeOutlookReadError.appNotFound(displayName)
        }

        let configuration = NSWorkspace.OpenConfiguration()
        configuration.activates = true
        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
            workspace.openApplication(at: appURL, configuration: configuration) { _, error in
                if let error {
                    continuation.resume(throwing: NativeOutlookReadError.openAppFailed(displayName, error.localizedDescription))
                } else {
                    continuation.resume(returning: ())
                }
            }
        }
    }

    private static func recognizeText(in image: CGImage) throws -> [String] {
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        request.usesLanguageCorrection = true
        request.recognitionLanguages = ["en-US", "zh-Hans", "zh-Hant"]

        let handler = VNImageRequestHandler(cgImage: image, options: [:])
        try handler.perform([request])

        let observations = request.results ?? []
        return observations.compactMap { observation in
            let line = observation.topCandidates(1).first?.string.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            return line.isEmpty ? nil : line
        }
    }

    private static func captureVisibleOutlookWindow() -> CGImage? {
        captureVisibleWindow(ownerNames: Set(["Microsoft Outlook"]))
    }

    private static func captureVisibleWindow(ownerNames: Set<String>? = nil) -> CGImage? {
        guard let windowInfo = CGWindowListCopyWindowInfo(
            [.optionOnScreenOnly, .excludeDesktopElements],
            kCGNullWindowID
        ) as? [[String: Any]] else {
            return nil
        }

        let candidates: [(windowID: CGWindowID, bounds: CGRect)] = windowInfo.compactMap { window in
            let ownerName = window[kCGWindowOwnerName as String] as? String ?? ""
            if let ownerNames {
                guard ownerNames.contains(ownerName) else {
                    return nil
                }
            } else if ownerName.localizedCaseInsensitiveContains("Jarvis") {
                return nil
            }
            let layer = window[kCGWindowLayer as String] as? Int ?? 0
            guard layer == 0 else {
                return nil
            }
            guard let number = window[kCGWindowNumber as String] as? NSNumber else {
                return nil
            }
            guard let boundsDictionary = window[kCGWindowBounds as String] as? NSDictionary,
                  let bounds = CGRect(dictionaryRepresentation: boundsDictionary) else {
                return nil
            }
            guard bounds.width >= 240, bounds.height >= 180 else {
                return nil
            }
            return (CGWindowID(number.uint32Value), bounds)
        }

        let selected = ownerNames == nil
            ? candidates.first
            : candidates.max(by: { lhs, rhs in
                lhs.bounds.width * lhs.bounds.height < rhs.bounds.width * rhs.bounds.height
            })
        guard let selected else {
            return nil
        }

        let imageOptions: CGWindowImageOption = [.boundsIgnoreFraming, .bestResolution]
        return CGWindowListCreateImage(
            .null,
            .optionIncludingWindow,
            selected.windowID,
            imageOptions
        ) ?? CGWindowListCreateImage(
            selected.bounds,
            [.optionOnScreenOnly],
            kCGNullWindowID,
            imageOptions
        )
    }

    static func failureDiagnostics(for error: Error, source: String = "native_vision_ocr") -> VisibleOutlookTextDiagnostics {
        VisibleOutlookTextDiagnostics(
            source: source,
            lineCount: 0,
            characterCount: 0,
            captureWidth: 0,
            captureHeight: 0,
            screenAccessPreflight: CGPreflightScreenCaptureAccess(),
            captureError: String(describing: error),
            appBundlePath: Bundle.main.bundleURL.path,
            appExecutablePath: Bundle.main.executableURL?.path ?? "",
            bundleIdentifier: Bundle.main.bundleIdentifier ?? ""
        )
    }
}

enum NativeOutlookReadError: Error, CustomStringConvertible {
    case appNotFound(String)
    case screenRecordingDenied
    case captureFailed
    case openAppFailed(String, String)

    var description: String {
        switch self {
        case .appNotFound(let appName):
            return "\(appName) was not found by bundle identifier or fallback path."
        case .screenRecordingDenied:
            return "Jarvis does not have Screen Recording permission for native screenshot capture."
        case .captureFailed:
            return "CoreGraphics could not create a native screen image."
        case .openAppFailed(let appName, let message):
            return "Could not open \(appName): \(message)"
        }
    }
}
