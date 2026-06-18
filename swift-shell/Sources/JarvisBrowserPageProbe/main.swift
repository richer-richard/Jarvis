import Foundation
import JarvisMacNative

@main
struct JarvisBrowserPageProbe {
    static func main() {
        let arguments = parseArguments(Array(CommandLine.arguments.dropFirst()))
        let result = JarvisNativeBrowserReader.readChromeActiveTab(
            includePageText: arguments.includePageText,
            textLimit: arguments.textLimit
        )
        writeJSON(result.jsonObject)
        Foundation.exit(result.status == "checked" ? 0 : 1)
    }

    private static func parseArguments(_ arguments: [String]) -> (includePageText: Bool, textLimit: Int) {
        var includePageText = false
        var textLimit = 6000
        var iterator = arguments.makeIterator()
        while let argument = iterator.next() {
            switch argument {
            case "--include-page-text":
                includePageText = true
            case "--text-limit":
                if let raw = iterator.next(), let value = Int(raw) {
                    textLimit = value
                }
            default:
                continue
            }
        }
        return (includePageText, textLimit)
    }

    private static func writeJSON(_ payload: [String: Any]) {
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
