import Foundation
import JarvisMacNative

@main
struct JarvisBrowserPermissionProbe {
    static func main() {
        let result = JarvisNativeBrowserPermission.chromeAutomationStatus()
        writeJSON(result.jsonObject)
        Foundation.exit(result.requiresUserAction ? 2 : result.isReady ? 0 : 1)
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
