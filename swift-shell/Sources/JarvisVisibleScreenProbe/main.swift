import Foundation
import JarvisClient
import JarvisMacNative

@main
struct JarvisVisibleScreenProbe {
    static func main() async {
        let arguments = parseArguments(Array(CommandLine.arguments.dropFirst()))
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]

        do {
            let capture = try await JarvisNativeOutlookReader.readVisibleScreenText(
                targetAppName: arguments.targetAppName,
                targetBundleIdentifier: arguments.targetBundleIdentifier
            )
            let payload: [String: Any] = [
                "status": "captured",
                "text": capture.text,
                "diagnostics": capture.diagnostics.jsonObject,
            ]
            writeJSON(payload, using: encoder)
            Foundation.exit(0)
        } catch {
            let diagnostics = JarvisNativeOutlookReader.failureDiagnostics(
                for: error,
                source: "native_vision_ocr_screen"
            )
            let payload: [String: Any] = [
                "status": "failed",
                "error": String(describing: error),
                "text": "",
                "diagnostics": diagnostics.jsonObject,
            ]
            writeJSON(payload, using: encoder)
            Foundation.exit(1)
        }
    }

    private static func parseArguments(_ arguments: [String]) -> (targetAppName: String?, targetBundleIdentifier: String?) {
        var targetAppName: String?
        var targetBundleIdentifier: String?
        var iterator = arguments.makeIterator()
        while let argument = iterator.next() {
            switch argument {
            case "--target-app-name":
                targetAppName = iterator.next()
            case "--target-bundle-id":
                targetBundleIdentifier = iterator.next()
            default:
                continue
            }
        }
        return (targetAppName, targetBundleIdentifier)
    }

    private static func writeJSON(_ payload: [String: Any], using encoder: JSONEncoder) {
        let data: Data
        if JSONSerialization.isValidJSONObject(payload),
           let serialized = try? JSONSerialization.data(withJSONObject: payload, options: [.prettyPrinted, .sortedKeys]) {
            data = serialized
        } else {
            data = Data("{\"status\":\"failed\",\"error\":\"json_encode_failed\"}".utf8)
        }
        if let text = String(data: data, encoding: .utf8) {
            FileHandle.standardOutput.write(Data(text.utf8))
            if !text.hasSuffix("\n") {
                FileHandle.standardOutput.write(Data("\n".utf8))
            }
        }
    }
}
