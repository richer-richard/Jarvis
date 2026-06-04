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

    @MainActor
    private static func focusOutlook() async throws {
        let workspace = NSWorkspace.shared
        let appURL = workspace.urlForApplication(withBundleIdentifier: "com.microsoft.Outlook")
            ?? URL(fileURLWithPath: "/Applications/Microsoft Outlook.app")
        guard FileManager.default.fileExists(atPath: appURL.path) else {
            throw NativeOutlookReadError.outlookNotFound
        }

        let configuration = NSWorkspace.OpenConfiguration()
        configuration.activates = true
        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
            workspace.openApplication(at: appURL, configuration: configuration) { _, error in
                if let error {
                    continuation.resume(throwing: NativeOutlookReadError.openOutlookFailed(error.localizedDescription))
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
        guard let windowInfo = CGWindowListCopyWindowInfo(
            [.optionOnScreenOnly, .excludeDesktopElements],
            kCGNullWindowID
        ) as? [[String: Any]] else {
            return nil
        }

        let candidates: [(windowID: CGWindowID, bounds: CGRect)] = windowInfo.compactMap { window in
            let ownerName = window[kCGWindowOwnerName as String] as? String ?? ""
            guard ownerName == "Microsoft Outlook" else {
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

        guard let largest = candidates.max(by: { lhs, rhs in
            lhs.bounds.width * lhs.bounds.height < rhs.bounds.width * rhs.bounds.height
        }) else {
            return nil
        }

        let imageOptions: CGWindowImageOption = [.boundsIgnoreFraming, .bestResolution]
        return CGWindowListCreateImage(
            .null,
            .optionIncludingWindow,
            largest.windowID,
            imageOptions
        ) ?? CGWindowListCreateImage(
            largest.bounds,
            [.optionOnScreenOnly],
            kCGNullWindowID,
            imageOptions
        )
    }

    static func failureDiagnostics(for error: Error) -> VisibleOutlookTextDiagnostics {
        VisibleOutlookTextDiagnostics(
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
    case outlookNotFound
    case screenRecordingDenied
    case captureFailed
    case openOutlookFailed(String)

    var description: String {
        switch self {
        case .outlookNotFound:
            return "Microsoft Outlook was not found in /Applications or by bundle identifier."
        case .screenRecordingDenied:
            return "Jarvis does not have Screen Recording permission for native screenshot capture."
        case .captureFailed:
            return "CoreGraphics could not create a native screen image."
        case .openOutlookFailed(let message):
            return "Could not open Microsoft Outlook: \(message)"
        }
    }
}
