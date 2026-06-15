import AppKit
import Darwin
import Foundation
import JarvisClient

@main
@MainActor
struct JarvisStatusHelperApp {
    static func main() {
        if CommandLine.arguments.contains("--self-test") {
            runSelfTest()
            return
        }
        let app = NSApplication.shared
        let delegate = JarvisStatusHelperDelegate(arguments: CommandLine.arguments)
        app.delegate = delegate
        app.setActivationPolicy(.accessory)
        app.run()
    }

    private static func runSelfTest() {
        let parsed = JarvisStatusHelperDelegate.parseArguments([
            "jarvis-status-helper",
            "--app-bundle-path",
            "/Applications/Jarvis.app",
            "--base-url",
            "http://127.0.0.1:8765",
            "--parent-pid",
            "12345",
        ])
        guard parsed.appBundlePath == "/Applications/Jarvis.app" else {
            fputs("Jarvis status helper self-test failed: app bundle path did not parse.\n", stderr)
            Foundation.exit(1)
        }
        guard parsed.baseURL?.absoluteString == "http://127.0.0.1:8765" else {
            fputs("Jarvis status helper self-test failed: base URL did not parse.\n", stderr)
            Foundation.exit(1)
        }
        guard parsed.parentPID == 12345 else {
            fputs("Jarvis status helper self-test failed: parent PID did not parse.\n", stderr)
            Foundation.exit(1)
        }
        guard JarvisStatusHelperDelegate.processExists(ProcessInfo.processInfo.processIdentifier) else {
            fputs("Jarvis status helper self-test failed: current process should exist.\n", stderr)
            Foundation.exit(1)
        }
        guard JarvisStatusHelperDelegate.speechMuteMenuTitle(muted: false) == "Shut Up" else {
            fputs("Jarvis status helper self-test failed: unmuted title should be Shut Up.\n", stderr)
            Foundation.exit(1)
        }
        guard JarvisStatusHelperDelegate.speechMuteMenuTitle(muted: true) == "Keep Blabbering" else {
            fputs("Jarvis status helper self-test failed: muted title should be Keep Blabbering.\n", stderr)
            Foundation.exit(1)
        }
        guard JarvisStatusHelperDelegate.musicStopMenuTitle == "Stop Music" else {
            fputs("Jarvis status helper self-test failed: music stop title changed.\n", stderr)
            Foundation.exit(1)
        }
        guard JarvisStatusHelperDelegate.audioUnmuteMenuTitle == "Unmute Audio" else {
            fputs("Jarvis status helper self-test failed: audio unmute title changed.\n", stderr)
            Foundation.exit(1)
        }
        guard MainAppNotification.openPanel.rawValue == "local.leo.jarvis.statusHelper.openPanel",
              MainAppNotification.runStatus.rawValue == "local.leo.jarvis.statusHelper.runStatus",
              MainAppNotification.toggleWakeListener.rawValue == "local.leo.jarvis.statusHelper.toggleWakeListener",
              MainAppNotification.speechMuteChanged.rawValue == "local.leo.jarvis.statusHelper.speechMuteChanged",
              MainAppNotification.quit.rawValue == "local.leo.jarvis.statusHelper.quit" else {
            fputs("Jarvis status helper self-test failed: notification names changed.\n", stderr)
            Foundation.exit(1)
        }
        print("Jarvis status helper self-test passed")
    }
}

@MainActor
final class JarvisStatusHelperDelegate: NSObject, NSApplicationDelegate, NSMenuDelegate {
    private let client: JarvisClient
    private let appBundleURL: URL?
    private let parentPID: pid_t?
    private var statusItem: NSStatusItem?
    private var speechMuteItem: NSMenuItem?
    private var knownMuted: Bool = false
    private var parentMonitor: Timer?

    init(arguments: [String]) {
        let parsed = Self.parseArguments(arguments)
        if let baseURL = parsed.baseURL {
            client = JarvisClient(baseURL: baseURL)
        } else {
            client = (try? JarvisClient.fromEnvironment()) ?? JarvisClient(baseURL: URL(string: "http://127.0.0.1:8765")!)
        }
        appBundleURL = parsed.appBundlePath.map(URL.init(fileURLWithPath:))
        parentPID = parsed.parentPID
        super.init()
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        configureStatusItem()
        refreshSpeechMuteTitle()
        startParentMonitor()
    }

    func applicationWillTerminate(_ notification: Notification) {
        parentMonitor?.invalidate()
        parentMonitor = nil
    }

    private func startParentMonitor() {
        guard let parentPID else {
            return
        }
        parentMonitor = Timer.scheduledTimer(withTimeInterval: 1.0, repeats: true) { [weak self] _ in
            Task { @MainActor in
                guard self != nil else {
                    return
                }
                if !Self.processExists(parentPID) {
                    NSApp.terminate(nil)
                }
            }
        }
    }

    private func configureStatusItem() {
        let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
        let image = Self.statusItemImage()
        item.button?.title = image == nil ? "J" : ""
        item.button?.image = image
        item.button?.imagePosition = image == nil ? .noImage : .imageOnly
        item.button?.imageScaling = .scaleProportionallyDown
        item.button?.toolTip = "Jarvis"
        item.button?.setAccessibilityLabel("Jarvis")

        let menu = NSMenu()
        menu.delegate = self
        let muteItem = NSMenuItem(title: Self.speechMuteMenuTitle(muted: knownMuted), action: #selector(toggleSpeechMute), keyEquivalent: "")
        speechMuteItem = muteItem
        menu.addItem(muteItem)
        menu.addItem(NSMenuItem(title: Self.musicStopMenuTitle, action: #selector(stopMusic), keyEquivalent: ""))
        menu.addItem(NSMenuItem(title: Self.audioUnmuteMenuTitle, action: #selector(unmuteAudio), keyEquivalent: ""))
        menu.addItem(.separator())
        menu.addItem(NSMenuItem(title: "Open Panel", action: #selector(openPanel), keyEquivalent: "o"))
        menu.addItem(NSMenuItem(title: "Run Status", action: #selector(runStatus), keyEquivalent: "r"))
        menu.addItem(NSMenuItem(title: "Open Dashboard", action: #selector(openDashboard), keyEquivalent: "d"))
        menu.addItem(NSMenuItem(title: "Open Overnight Report", action: #selector(openOvernightReport), keyEquivalent: ""))
        menu.addItem(NSMenuItem(title: "Open Wake Test", action: #selector(openWakeTest), keyEquivalent: ""))
        menu.addItem(NSMenuItem(title: "Toggle Hey Jarvis", action: #selector(toggleWakeListener), keyEquivalent: ""))
        menu.addItem(.separator())
        menu.addItem(NSMenuItem(title: "Quit Jarvis", action: #selector(quitJarvis), keyEquivalent: "q"))
        for item in menu.items {
            item.target = self
        }
        item.menu = menu
        statusItem = item
    }

    func menuNeedsUpdate(_ menu: NSMenu) {
        refreshSpeechMuteTitle()
    }

    private func refreshSpeechMuteTitle() {
        Task {
            do {
                let status = try await client.speechMuteStatus()
                knownMuted = status.muted
                speechMuteItem?.title = Self.speechMuteMenuTitle(muted: status.muted)
            } catch {
                speechMuteItem?.title = Self.speechMuteMenuTitle(muted: knownMuted)
            }
        }
    }

    @objc private func toggleSpeechMute() {
        let target = !knownMuted
        knownMuted = target
        speechMuteItem?.title = Self.speechMuteMenuTitle(muted: target)
        Task {
            do {
                let response = try await client.setSpeechMuted(target, source: "status_helper")
                knownMuted = response.muted
                speechMuteItem?.title = Self.speechMuteMenuTitle(muted: response.muted)
                postMainAppNotification(.speechMuteChanged)
            } catch {
                knownMuted.toggle()
                speechMuteItem?.title = Self.speechMuteMenuTitle(muted: knownMuted)
            }
        }
    }

    @objc private func stopMusic() {
        Task {
            _ = try? await client.stopMusic()
        }
    }

    @objc private func unmuteAudio() {
        Task {
            _ = try? await client.unmuteSystemAudio()
        }
    }

    @objc private func openPanel() {
        postMainAppNotification(.openPanel)
        openMainApp()
    }

    @objc private func runStatus() {
        postMainAppNotification(.runStatus)
        openMainApp()
    }

    @objc private func openDashboard() {
        openMainApp()
        NSWorkspace.shared.open(client.baseURL)
    }

    @objc private func openOvernightReport() {
        openMainApp()
        NSWorkspace.shared.open(client.baseURL.appendingPathComponent("overnight-report/"))
    }

    @objc private func openWakeTest() {
        openMainApp()
        NSWorkspace.shared.open(client.baseURL.appendingPathComponent("wake-audition/"))
    }

    @objc private func toggleWakeListener() {
        postMainAppNotification(.toggleWakeListener)
        openMainApp()
    }

    @objc private func quitJarvis() {
        postMainAppNotification(.quit)
        NSApp.terminate(nil)
    }

    private func openMainApp() {
        guard let appBundleURL else {
            return
        }
        NSWorkspace.shared.openApplication(
            at: appBundleURL,
            configuration: NSWorkspace.OpenConfiguration()
        )
    }

    private func postMainAppNotification(_ notification: MainAppNotification) {
        DistributedNotificationCenter.default().postNotificationName(
            notification.name,
            object: nil,
            userInfo: nil,
            deliverImmediately: true
        )
    }

    private static func statusItemImage() -> NSImage? {
        let url = Bundle.main.url(forResource: "JarvisMenuHead", withExtension: "png")
            ?? Bundle.main.url(forResource: "JarvisLogo", withExtension: "png")
        guard let url,
              let loadedImage = NSImage(contentsOf: url),
              let image = loadedImage.copy() as? NSImage else {
            return nil
        }
        image.size = NSSize(width: 20, height: 20)
        image.isTemplate = false
        return image
    }

    fileprivate static func speechMuteMenuTitle(muted: Bool) -> String {
        muted ? "Keep Blabbering" : "Shut Up"
    }

    fileprivate static var musicStopMenuTitle: String {
        "Stop Music"
    }

    fileprivate static var audioUnmuteMenuTitle: String {
        "Unmute Audio"
    }

    fileprivate static func parseArguments(_ arguments: [String]) -> (appBundlePath: String?, baseURL: URL?, parentPID: pid_t?) {
        var appBundlePath: String?
        var baseURL: URL?
        var parentPID: pid_t?
        var iterator = arguments.dropFirst().makeIterator()
        while let argument = iterator.next() {
            switch argument {
            case "--app-bundle-path":
                appBundlePath = iterator.next()
            case "--base-url":
                if let value = iterator.next() {
                    baseURL = URL(string: value)
                }
            case "--parent-pid":
                if let value = iterator.next(), let parsed = Int32(value), parsed > 1 {
                    parentPID = pid_t(parsed)
                }
            default:
                continue
            }
        }
        return (appBundlePath, baseURL, parentPID)
    }

    nonisolated fileprivate static func processExists(_ pid: pid_t) -> Bool {
        guard pid > 1 else {
            return false
        }
        errno = 0
        if kill(pid, 0) == 0 {
            return true
        }
        return errno == EPERM
    }
}

private enum MainAppNotification: String {
    case openPanel = "local.leo.jarvis.statusHelper.openPanel"
    case runStatus = "local.leo.jarvis.statusHelper.runStatus"
    case toggleWakeListener = "local.leo.jarvis.statusHelper.toggleWakeListener"
    case speechMuteChanged = "local.leo.jarvis.statusHelper.speechMuteChanged"
    case quit = "local.leo.jarvis.statusHelper.quit"

    var name: Notification.Name {
        Notification.Name(rawValue)
    }
}
