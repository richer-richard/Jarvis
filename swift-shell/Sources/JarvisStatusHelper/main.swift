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
        guard JarvisStatusHelperDelegate.statusItemFallbackTitle.isEmpty else {
            fputs("Jarvis status helper self-test failed: status item must not fall back to a text icon.\n", stderr)
            Foundation.exit(1)
        }
        if Bundle.main.bundleURL.pathExtension == "app" {
            guard JarvisStatusHelperDelegate.statusItemImage() != nil else {
                fputs("Jarvis status helper self-test failed: bundled menu head image did not load.\n", stderr)
                Foundation.exit(1)
            }
        }
        guard !JarvisStatusHelperDelegate.shouldOpenStatusMenu(eventType: .leftMouseUp, modifierFlags: []) else {
            fputs("Jarvis status helper self-test failed: left-click should open the Jarvis window.\n", stderr)
            Foundation.exit(1)
        }
        guard JarvisStatusHelperDelegate.shouldOpenStatusMenu(eventType: .rightMouseUp, modifierFlags: []) else {
            fputs("Jarvis status helper self-test failed: right-click should open the emergency menu.\n", stderr)
            Foundation.exit(1)
        }
        guard JarvisStatusHelperDelegate.shouldOpenStatusMenu(eventType: .leftMouseUp, modifierFlags: [.control]) else {
            fputs("Jarvis status helper self-test failed: Control-click should open the emergency menu.\n", stderr)
            Foundation.exit(1)
        }
        // Independent of Bundle.main: pin the fallback identifier to its literal
        // value. The notification-name checks below cannot catch a drift in this
        // constant because both operands derive from the same runtime value -- when
        // Bundle.main.bundleIdentifier is nil (e.g. `swift run`) both sides resolve
        // to this same fallback, so the prefix comparison is tautological. This
        // literal assertion is the only part of the self-test that would fail if
        // someone changed fallbackBundleIdentifier here (or in JarvisMenuBarApp's
        // matching copy) and forgot to update the other.
        guard MainAppNotification.fallbackBundleIdentifier == "local.leo.jarvis" else {
            fputs("Jarvis status helper self-test failed: fallback bundle identifier drifted from local.leo.jarvis; JarvisMenuBarApp.swift's matching copy must be kept in sync.\n", stderr)
            Foundation.exit(1)
        }
        let notificationPrefix = Bundle.main.bundleIdentifier ?? MainAppNotification.fallbackBundleIdentifier
        guard MainAppNotification.openPanel.name.rawValue == "\(notificationPrefix).statusHelper.openPanel",
              MainAppNotification.runStatus.name.rawValue == "\(notificationPrefix).statusHelper.runStatus",
              MainAppNotification.toggleWakeListener.name.rawValue == "\(notificationPrefix).statusHelper.toggleWakeListener",
              MainAppNotification.stopMusic.name.rawValue == "\(notificationPrefix).statusHelper.stopMusic",
              MainAppNotification.speechMuteChanged.name.rawValue == "\(notificationPrefix).statusHelper.speechMuteChanged",
              MainAppNotification.quit.name.rawValue == "\(notificationPrefix).statusHelper.quit" else {
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
    private var statusMenu: NSMenu?
    private var speechMuteItem: NSMenuItem?
    private var knownMuted: Bool = false
    private var parentMonitor: Timer?

    init(arguments: [String]) {
        let parsed = Self.parseArguments(arguments)
        if let baseURL = parsed.baseURL, JarvisClient.isLoopbackURL(baseURL) {
            client = JarvisClient(baseURL: baseURL)
        } else {
            client = (try? JarvisClient.fromEnvironment()) ?? JarvisClient(baseURL: URL(string: "http://127.0.0.1:8765")!)
        }
        appBundleURL = parsed.appBundlePath.map(URL.init(fileURLWithPath:))
        parentPID = parsed.parentPID
        super.init()
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        Self.warnIfBundleIdentityCannotRouteNotifications()
        configureStatusItem()
        refreshSpeechMuteTitle()
        startParentMonitor()
    }

    // Real-world (not --self-test) sanity check for the invariant documented on
    // MainAppNotification: this helper must run from inside the main app's
    // Contents/MacOS/ so Bundle.main resolves to that .app and reports its
    // CFBundleIdentifier. If we are bundled in an .app yet have no bundle
    // identifier, every cross-process notification silently falls back to
    // `local.leo.jarvis` and may not match a rebranded main app -- surface that
    // here instead of failing invisibly.
    private static func warnIfBundleIdentityCannotRouteNotifications() {
        guard Bundle.main.bundleURL.pathExtension == "app" else {
            return
        }
        if Bundle.main.bundleIdentifier == nil {
            fputs(
                "Jarvis status helper warning: running from an .app bundle but Bundle.main.bundleIdentifier is nil; cross-process notifications will fall back to \(MainAppNotification.fallbackBundleIdentifier) and may not reach the main app.\n",
                stderr
            )
        }
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
        item.button?.title = Self.statusItemFallbackTitle
        item.button?.image = image
        item.button?.imagePosition = .imageOnly
        item.button?.imageScaling = .scaleProportionallyDown
        item.button?.toolTip = "Jarvis"
        item.button?.setAccessibilityLabel("Jarvis")
        item.button?.target = self
        item.button?.action = #selector(statusItemClicked(_:))
        item.button?.sendAction(on: [.leftMouseUp, .rightMouseUp])

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
        menu.addItem(NSMenuItem(title: "Open Questions", action: #selector(openCapabilityQuestions), keyEquivalent: ""))
        menu.addItem(NSMenuItem(title: "Open Wake Test", action: #selector(openWakeTest), keyEquivalent: ""))
        menu.addItem(NSMenuItem(title: "Toggle Hey Jarvis", action: #selector(toggleWakeListener), keyEquivalent: ""))
        menu.addItem(.separator())
        menu.addItem(NSMenuItem(title: "Quit Jarvis", action: #selector(quitJarvis), keyEquivalent: "q"))
        for item in menu.items {
            item.target = self
        }
        statusMenu = menu
        statusItem = item
    }

    func menuNeedsUpdate(_ menu: NSMenu) {
        refreshSpeechMuteTitle()
    }

    @objc private func statusItemClicked(_ sender: NSStatusBarButton) {
        let event = NSApp.currentEvent
        if Self.shouldOpenStatusMenu(eventType: event?.type, modifierFlags: event?.modifierFlags ?? []) {
            showStatusMenu(from: sender)
            return
        }
        openPanel()
    }

    fileprivate static func shouldOpenStatusMenu(
        eventType: NSEvent.EventType?,
        modifierFlags: NSEvent.ModifierFlags
    ) -> Bool {
        eventType == .rightMouseUp || modifierFlags.contains(.control)
    }

    private func showStatusMenu(from sender: NSStatusBarButton? = nil) {
        guard let statusMenu else {
            openPanel()
            return
        }
        refreshSpeechMuteTitle()
        let sourceView = sender ?? statusItem?.button
        guard let sourceView else {
            openPanel()
            return
        }
        statusMenu.popUp(positioning: nil, at: NSPoint(x: 0, y: sourceView.bounds.height + 4), in: sourceView)
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
                if target {
                    _ = try? await client.stopSpeaking()
                }
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
            postMainAppNotification(.stopMusic)
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

    @objc private func openCapabilityQuestions() {
        openMainApp()
        NSWorkspace.shared.open(client.baseURL.appendingPathComponent("capability-questions/"))
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

    fileprivate static func statusItemImage() -> NSImage? {
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

    fileprivate static var statusItemFallbackTitle: String {
        ""
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
    case openPanel = "statusHelper.openPanel"
    case runStatus = "statusHelper.runStatus"
    case toggleWakeListener = "statusHelper.toggleWakeListener"
    case stopMusic = "statusHelper.stopMusic"
    case speechMuteChanged = "statusHelper.speechMuteChanged"
    case quit = "statusHelper.quit"

    // SYNC WITH: JarvisMenuBar/App/JarvisMenuBarApp.swift, which keeps its OWN
    // identical copy of this enum. The main app and this status helper are two
    // separate executable targets, so neither can import the other's private
    // enum -- the duplication is deliberate. The two copies MUST stay identical:
    // same case rawValues, same `fallbackBundleIdentifier` literal, and same
    // `name` computation. If they diverge, the two processes derive different
    // DistributedNotificationCenter names and silently stop talking to each
    // other. Nothing verifies this match across the process boundary at build or
    // run time (the --self-test above only checks this process's internal
    // self-consistency plus the pinned fallback literal), so any edit here MUST
    // be mirrored by hand in JarvisMenuBarApp.swift's copy, and vice versa.
    //
    // Keep the legacy bundle id as the fallback so `swift run` (no bundle, nil
    // bundleIdentifier) and the default `local.leo.jarvis` build produce the exact
    // same notification names as before, while a rebranded BUNDLE_ID keeps the main
    // app and this separate status-helper process routed to matching names.
    //
    // IMPORTANT: this only works because this helper binary is launched from
    // inside the app bundle's own Contents/MacOS/ (see build_app_bundle.sh and
    // JarvisMenuBarApp.swift's startStatusHelper()), which makes `Bundle.main`
    // here resolve to the ENCLOSING .app and report the app's own
    // CFBundleIdentifier. If this helper is ever moved elsewhere (its own
    // Contents/Helpers/ location, its own Info.plist, an XPC service, etc.),
    // `Bundle.main.bundleIdentifier` here would silently stop matching the main
    // app's, and every cross-process notification below would silently stop
    // firing -- with no compile error and no test catching it (the --self-test
    // below only checks internal self-consistency, not a match against the
    // running main app). Keep this helper inside the main app's Contents/MacOS/.
    fileprivate static let fallbackBundleIdentifier = "local.leo.jarvis"

    var name: Notification.Name {
        let prefix = Bundle.main.bundleIdentifier ?? Self.fallbackBundleIdentifier
        return Notification.Name("\(prefix).\(rawValue)")
    }
}
