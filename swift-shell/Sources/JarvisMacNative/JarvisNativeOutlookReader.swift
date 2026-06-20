import AppKit
import CoreGraphics
import Foundation
import JarvisClient
import Vision

public struct NativeOutlookOCRResult: Sendable {
    public let text: String
    public let diagnostics: VisibleOutlookTextDiagnostics
    public let lines: [NativeOCRLine]

    public init(text: String, diagnostics: VisibleOutlookTextDiagnostics, lines: [NativeOCRLine] = []) {
        self.text = text
        self.diagnostics = diagnostics
        self.lines = lines
    }
}

public struct NativeOCRLine: Sendable {
    public let text: String
    public let boundingBox: CGRect
    public let imageWidth: Int
    public let imageHeight: Int

    public var jsonObject: [String: Any] {
        [
            "text": text,
            "normalized": [
                "x": boundingBox.origin.x,
                "y": boundingBox.origin.y,
                "width": boundingBox.width,
                "height": boundingBox.height,
            ],
            "pixels": [
                "x": boundingBox.origin.x * CGFloat(imageWidth),
                "y": (1.0 - boundingBox.origin.y - boundingBox.height) * CGFloat(imageHeight),
                "width": boundingBox.width * CGFloat(imageWidth),
                "height": boundingBox.height * CGFloat(imageHeight),
            ],
        ]
    }
}

private struct NativeWindowCapture {
    let image: CGImage
    let bounds: CGRect
    let ownerName: String
    let windowTitle: String
}

public enum JarvisNativeOutlookReader {
    public static func readVisibleOutlookText() async throws -> NativeOutlookOCRResult {
        try await focusOutlook()
        try await Task.sleep(nanoseconds: 1_200_000_000)

        let hadAccessBeforeRequest = CGPreflightScreenCaptureAccess()
        if !hadAccessBeforeRequest {
            let granted = CGRequestScreenCaptureAccess()
            guard granted else {
                throw NativeOutlookReadError.screenRecordingDenied
            }
        }

        let windowCapture = captureVisibleOutlookWindow()
        guard let image = windowCapture?.image ?? CGDisplayCreateImage(CGMainDisplayID()) else {
            throw NativeOutlookReadError.captureFailed
        }

        let lines = try recognizeTextLines(in: image)
        let text = String(lines.map(\.text).joined(separator: "\n").prefix(12_000))
        return NativeOutlookOCRResult(
            text: text,
            diagnostics: VisibleOutlookTextDiagnostics(
                lineCount: lines.count,
                characterCount: text.count,
                captureWidth: image.width,
                captureHeight: image.height,
                captureBoundsX: double(windowCapture?.bounds.origin.x),
                captureBoundsY: double(windowCapture?.bounds.origin.y),
                captureBoundsWidth: double(windowCapture?.bounds.width),
                captureBoundsHeight: double(windowCapture?.bounds.height),
                captureScaleX: captureScale(imagePixels: image.width, screenPoints: windowCapture?.bounds.width),
                captureScaleY: captureScale(imagePixels: image.height, screenPoints: windowCapture?.bounds.height),
                screenAccessPreflight: hadAccessBeforeRequest,
                captureError: nil,
                appBundlePath: Bundle.main.bundleURL.path,
                appExecutablePath: Bundle.main.executableURL?.path ?? "",
                bundleIdentifier: Bundle.main.bundleIdentifier ?? "",
                windowTitle: windowCapture?.windowTitle ?? ""
            ),
            lines: lines
        )
    }

    public static func readVisibleScreenText(
        targetAppName: String? = nil,
        targetBundleIdentifier: String? = nil,
        preferredWindowTitleContains: String? = nil
    ) async throws -> NativeOutlookOCRResult {
        let cleanTargetName = targetAppName?.trimmingCharacters(in: .whitespacesAndNewlines)
        let cleanBundleIdentifier = targetBundleIdentifier?.trimmingCharacters(in: .whitespacesAndNewlines)
        let cleanPreferredWindowTitle = preferredWindowTitleContains?.trimmingCharacters(in: .whitespacesAndNewlines)
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
        let initialWindowCapture = captureVisibleWindow(
            ownerNames: ownerNames,
            preferredWindowTitleContains: cleanPreferredWindowTitle?.isEmpty == false ? cleanPreferredWindowTitle : nil
        )
        guard let initialImage = initialWindowCapture?.image ?? CGDisplayCreateImage(CGMainDisplayID()) else {
            throw NativeOutlookReadError.captureFailed
        }

        var image = initialImage
        var windowCapture = initialWindowCapture
        var lines = try recognizeTextLines(in: image)
        var source = initialWindowCapture == nil ? "native_vision_ocr_screen_display_fallback" : "native_vision_ocr_screen"
        let initialText = lines.map(\.text).joined(separator: "\n").trimmingCharacters(in: .whitespacesAndNewlines)
        if (lines.isEmpty || lines.count <= 2 || initialText.count < 80),
           ownerNames != nil,
           let displayImage = CGDisplayCreateImage(CGMainDisplayID()) {
            let displayLines = try recognizeTextLines(in: displayImage)
            let displayText = displayLines.map(\.text).joined(separator: "\n").trimmingCharacters(in: .whitespacesAndNewlines)
            if displayLines.count > lines.count || displayText.count > initialText.count + 80 {
                image = displayImage
                windowCapture = nil
                lines = displayLines
                source = "native_vision_ocr_screen_display_fallback"
            }
        }
        let text = String(lines.map(\.text).joined(separator: "\n").prefix(12_000))
        return NativeOutlookOCRResult(
            text: text,
            diagnostics: VisibleOutlookTextDiagnostics(
                source: source,
                lineCount: lines.count,
                characterCount: text.count,
                captureWidth: image.width,
                captureHeight: image.height,
                captureBoundsX: double(windowCapture?.bounds.origin.x),
                captureBoundsY: double(windowCapture?.bounds.origin.y),
                captureBoundsWidth: double(windowCapture?.bounds.width),
                captureBoundsHeight: double(windowCapture?.bounds.height),
                captureScaleX: captureScale(imagePixels: image.width, screenPoints: windowCapture?.bounds.width),
                captureScaleY: captureScale(imagePixels: image.height, screenPoints: windowCapture?.bounds.height),
                screenAccessPreflight: hadAccessBeforeRequest,
                captureError: nil,
                appBundlePath: Bundle.main.bundleURL.path,
                appExecutablePath: Bundle.main.executableURL?.path ?? "",
                bundleIdentifier: Bundle.main.bundleIdentifier ?? "",
                targetAppName: cleanTargetName ?? "",
                windowTitle: windowCapture?.windowTitle ?? ""
            ),
            lines: lines
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
        try recognizeTextLines(in: image).map(\.text)
    }

    private static func recognizeTextLines(in image: CGImage) throws -> [NativeOCRLine] {
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        request.usesLanguageCorrection = true
        request.recognitionLanguages = ["en-US", "zh-Hans", "zh-Hant"]

        let handler = VNImageRequestHandler(cgImage: image, options: [:])
        try handler.perform([request])

        let observations = request.results ?? []
        return observations.compactMap { observation in
            let line = observation.topCandidates(1).first?.string.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            if line.isEmpty {
                return nil
            }
            return NativeOCRLine(
                text: line,
                boundingBox: observation.boundingBox,
                imageWidth: image.width,
                imageHeight: image.height
            )
        }
    }

    private static func captureVisibleOutlookWindow() -> NativeWindowCapture? {
        captureVisibleWindow(ownerNames: Set(["Microsoft Outlook"]))
    }

    private static func captureVisibleWindow(
        ownerNames: Set<String>? = nil,
        preferredWindowTitleContains: String? = nil
    ) -> NativeWindowCapture? {
        guard let windowInfo = CGWindowListCopyWindowInfo(
            [.optionOnScreenOnly, .excludeDesktopElements],
            kCGNullWindowID
        ) as? [[String: Any]] else {
            return nil
        }
        let preferredTitle = preferredWindowTitleContains?.trimmingCharacters(in: .whitespacesAndNewlines)

        let candidates: [(windowID: CGWindowID, bounds: CGRect, ownerName: String, windowTitle: String)] = windowInfo.compactMap { window in
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
            let windowTitle = window[kCGWindowName as String] as? String ?? ""
            return (CGWindowID(number.uint32Value), bounds, ownerName, windowTitle)
        }

        let selected: (windowID: CGWindowID, bounds: CGRect, ownerName: String, windowTitle: String)?
        if let preferredTitle, !preferredTitle.isEmpty,
           let matchingCandidate = candidates.first(where: { candidate in
               candidate.windowTitle.localizedCaseInsensitiveContains(preferredTitle)
           }) {
            selected = matchingCandidate
        } else if preferredTitle?.isEmpty == false {
            selected = candidates.first
        } else {
            selected = candidates.first
        }
        guard let selected else {
            if ownerNames?.contains("Google Chrome") == true {
                return captureChromeFrontWindowViaAppleScript()
            }
            return nil
        }

        let imageOptions: CGWindowImageOption = [.boundsIgnoreFraming, .bestResolution]
        let image = CGWindowListCreateImage(
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
        if image == nil, selected.ownerName == "Google Chrome" {
            return captureChromeFrontWindowViaAppleScript()
        }
        guard let image else {
            return nil
        }
        return NativeWindowCapture(
            image: image,
            bounds: selected.bounds,
            ownerName: selected.ownerName,
            windowTitle: selected.windowTitle
        )
    }

    private static func captureChromeFrontWindowViaAppleScript() -> NativeWindowCapture? {
        let script = """
        tell application "Google Chrome"
            if (count of windows) is 0 then return ""
            set windowBounds to bounds of front window
            set activeTitle to title of active tab of front window
            return activeTitle & linefeed & (item 1 of windowBounds as text) & "," & (item 2 of windowBounds as text) & "," & (item 3 of windowBounds as text) & "," & (item 4 of windowBounds as text)
        end tell
        """
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/osascript")
        process.arguments = ["-e", script]
        let output = Pipe()
        process.standardOutput = output
        process.standardError = Pipe()
        do {
            try process.run()
            process.waitUntilExit()
        } catch {
            return nil
        }
        guard process.terminationStatus == 0 else {
            return nil
        }
        let data = output.fileHandleForReading.readDataToEndOfFile()
        guard let stdout = String(data: data, encoding: .utf8) else {
            return nil
        }
        let parts = stdout.split(separator: "\n", omittingEmptySubsequences: false)
        guard parts.count >= 2 else {
            return nil
        }
        let title = String(parts[0]).trimmingCharacters(in: .whitespacesAndNewlines)
        let values = parts[1].split(separator: ",").compactMap { Double($0.trimmingCharacters(in: .whitespacesAndNewlines)) }
        guard values.count == 4 else {
            return nil
        }
        let bounds = CGRect(
            x: values[0],
            y: values[1],
            width: max(0, values[2] - values[0]),
            height: max(0, values[3] - values[1])
        )
        guard bounds.width >= 240, bounds.height >= 180,
              let displayImage = CGDisplayCreateImage(CGMainDisplayID()) else {
            return nil
        }
        let displayBounds = CGDisplayBounds(CGMainDisplayID())
        let scaleX = CGFloat(displayImage.width) / max(displayBounds.width, 1)
        let scaleY = CGFloat(displayImage.height) / max(displayBounds.height, 1)
        var crop = CGRect(
            x: (bounds.origin.x - displayBounds.origin.x) * scaleX,
            y: (bounds.origin.y - displayBounds.origin.y) * scaleY,
            width: bounds.width * scaleX,
            height: bounds.height * scaleY
        ).integral
        let imageRect = CGRect(x: 0, y: 0, width: displayImage.width, height: displayImage.height)
        crop = crop.intersection(imageRect)
        guard crop.width > 0, crop.height > 0,
              let croppedImage = displayImage.cropping(to: crop) else {
            return nil
        }
        return NativeWindowCapture(
            image: croppedImage,
            bounds: bounds,
            ownerName: "Google Chrome",
            windowTitle: title
        )
    }

    private static func captureScale(imagePixels: Int, screenPoints: CGFloat?) -> Double {
        guard let screenPoints, screenPoints > 0 else {
            return 0
        }
        return Double(imagePixels) / Double(screenPoints)
    }

    private static func double(_ value: CGFloat?) -> Double {
        guard let value else {
            return 0
        }
        return Double(value)
    }

    public static func failureDiagnostics(
        for error: Error,
        source: String = "native_vision_ocr"
    ) -> VisibleOutlookTextDiagnostics {
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

public enum NativeOutlookReadError: Error, CustomStringConvertible {
    case appNotFound(String)
    case screenRecordingDenied
    case captureFailed
    case openAppFailed(String, String)

    public var description: String {
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
