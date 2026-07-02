import AppKit
import Combine
import CoreGraphics
import Foundation
import JarvisClient
import SwiftUI

@main
struct JarvisMenuBarApp {
    static func main() {
        if let fileTest = speechFileSelfTestArguments(CommandLine.arguments) {
            runSpeechFileSelfTest(audioPath: fileTest.audioPath, outputPath: fileTest.outputPath)
            return
        }
        if CommandLine.arguments.contains("--hotkey-self-test") {
            runHotKeySelfTest()
            return
        }
        if CommandLine.arguments.contains("--permission-self-test") {
            runPermissionSelfTest()
            return
        }
        if CommandLine.arguments.contains("--wake-permission-self-test") {
            runWakePermissionSelfTest()
            return
        }
        if CommandLine.arguments.contains("--wake-start-self-test") {
            runWakeStartSelfTest()
            return
        }
        if CommandLine.arguments.contains("--wake-soak-self-test") {
            runWakeSoakSelfTest()
            return
        }
        if CommandLine.arguments.contains("--routing-self-test") {
            runRoutingSelfTest()
            return
        }
        if CommandLine.arguments.contains("--worker-monitor-self-test") {
            runWorkerMonitorSelfTest()
            return
        }
        if CommandLine.arguments.contains("--worker-concurrency-self-test") {
            runWorkerConcurrencySelfTest()
            return
        }
        if CommandLine.arguments.contains("--worker-autostart-disabled-self-test") {
            runWorkerAutostartDisabledSelfTest()
            return
        }
        if CommandLine.arguments.contains("--window-self-test") {
            runWindowSelfTest()
            return
        }
        if CommandLine.arguments.contains("--self-test") {
            runSelfTest()
            return
        }

        let app = NSApplication.shared
        let delegate = JarvisAppDelegate()
        app.delegate = delegate
        app.setActivationPolicy(Self.activationPolicy())
        app.run()
    }

    private static func speechFileSelfTestArguments(_ arguments: [String]) -> (audioPath: String, outputPath: String)? {
        guard let index = arguments.firstIndex(of: "--stt-file-self-test"),
              arguments.count > index + 2 else {
            return nil
        }
        return (arguments[index + 1], arguments[index + 2])
    }

    static func activationPolicy(environment: [String: String] = ProcessInfo.processInfo.environment) -> NSApplication.ActivationPolicy {
        environmentFlag("JARVIS_SHOW_DOCK_ICON", environment: environment) == false ? .accessory : .regular
    }

    static func environmentFlag(_ name: String, environment: [String: String] = ProcessInfo.processInfo.environment) -> Bool? {
        guard let rawValue = environment[name]?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() else {
            return nil
        }
        if ["1", "true", "yes", "on"].contains(rawValue) {
            return true
        }
        if ["0", "false", "no", "off"].contains(rawValue) {
            return false
        }
        return nil
    }

    private static func runSelfTest() {
        Task {
            do {
                try await JarvisMenuBarSelfTest.run()
                Foundation.exit(0)
            } catch {
                fputs("Jarvis menu-bar self-test failed: \(error)\n", stderr)
                Foundation.exit(1)
            }
        }

        RunLoop.main.run()
    }

    private static func runRoutingSelfTest() {
        Task {
            do {
                try await JarvisMenuBarSelfTest.runCommandRoutingSelfTest()
                print("Jarvis command routing self-test passed")
                Foundation.exit(0)
            } catch {
                fputs("Jarvis command routing self-test failed: \(error)\n", stderr)
                Foundation.exit(1)
            }
        }

        RunLoop.main.run()
    }

    private static func runHotKeySelfTest() {
        let service = JarvisHotKeyService {}
        let result = service.start()
        print(result.description)
        service.stop()
        Foundation.exit(result.isRegistered ? 0 : 1)
    }

    private static func runPermissionSelfTest() {
        Task {
            do {
                try await JarvisMenuBarSelfTest.runPermissionReadiness()
                Foundation.exit(0)
            } catch {
                fputs("Jarvis permission self-test failed: \(error)\n", stderr)
                Foundation.exit(1)
            }
        }

        RunLoop.main.run()
    }

    private static func runSpeechFileSelfTest(audioPath: String, outputPath: String) {
        Task {
            do {
                try await JarvisMenuBarSelfTest.runSpeechFileTranscription(audioPath: audioPath, outputPath: outputPath)
                Foundation.exit(0)
            } catch {
                try? JarvisMenuBarSelfTest.writeJSON(
                    [
                        "status": "failed",
                        "error": "\(error)",
                        "audio_path": audioPath,
                    ],
                    to: outputPath
                )
                Foundation.exit(1)
            }
        }

        RunLoop.main.run()
    }

    private static func runWakePermissionSelfTest() {
        Task {
            do {
                try await JarvisMenuBarSelfTest.runWakePermissionCallbacks()
                Foundation.exit(0)
            } catch {
                fputs("Jarvis wake permission self-test failed: \(error)\n", stderr)
                Foundation.exit(1)
            }
        }

        RunLoop.main.run()
    }

    private static func runWakeStartSelfTest() {
        Task { @MainActor in
            do {
                try await JarvisMenuBarSelfTest.runWakeStartStop()
                Foundation.exit(0)
            } catch {
                fputs("Jarvis wake start self-test failed: \(error)\n", stderr)
                Foundation.exit(1)
            }
        }

        RunLoop.main.run()
    }

    private static func runWakeSoakSelfTest() {
        Task { @MainActor in
            do {
                try await JarvisMenuBarSelfTest.runWakeStartStop(durationSeconds: 35)
                Foundation.exit(0)
            } catch {
                fputs("Jarvis wake soak self-test failed: \(error)\n", stderr)
                Foundation.exit(1)
            }
        }

        RunLoop.main.run()
    }

    private static func runWorkerMonitorSelfTest() {
        Task {
            do {
                try await JarvisMenuBarSelfTest.runWorkerMonitorRecovery()
                Foundation.exit(0)
            } catch {
                fputs("Jarvis worker monitor self-test failed: \(error)\n", stderr)
                Foundation.exit(1)
            }
        }

        RunLoop.main.run()
    }

    private static func runWorkerConcurrencySelfTest() {
        Task {
            do {
                try await JarvisMenuBarSelfTest.runWorkerStartupConcurrency()
                Foundation.exit(0)
            } catch {
                fputs("Jarvis worker concurrency self-test failed: \(error)\n", stderr)
                Foundation.exit(1)
            }
        }

        RunLoop.main.run()
    }

    private static func runWorkerAutostartDisabledSelfTest() {
        Task {
            do {
                try await JarvisMenuBarSelfTest.runWorkerAutostartDisabled()
                Foundation.exit(0)
            } catch {
                fputs("Jarvis worker autostart-disabled self-test failed: \(error)\n", stderr)
                Foundation.exit(1)
            }
        }

        RunLoop.main.run()
    }

    @MainActor
    private static func runWindowSelfTest() {
        let app = NSApplication.shared
        let delegate = JarvisAppDelegate(selfTestMode: true)
        app.delegate = delegate
        app.setActivationPolicy(.regular)
        app.finishLaunching()

        Task { @MainActor in
            delegate.debugOpenPanelForSelfTest()
            try? await Task.sleep(nanoseconds: 200_000_000)
            var snapshots: [[String: Any]] = []
            snapshots.append(delegate.debugWindowSnapshot(label: "after_open_panel"))

            delegate.debugStartStatusHelperForSelfTest()
            try? await Task.sleep(nanoseconds: 200_000_000)
            snapshots.append(delegate.debugWindowSnapshot(label: "after_status_helper"))

            delegate.debugRefreshModelForSelfTest()
            try? await Task.sleep(nanoseconds: 400_000_000)
            snapshots.append(delegate.debugWindowSnapshot(label: "after_refresh"))

            let finalSnapshot = snapshots.last ?? [:]
            let snapshot: [String: Any] = [
                "snapshots": snapshots,
            ]
            do {
                let data = try JSONSerialization.data(withJSONObject: snapshot, options: [.prettyPrinted, .sortedKeys])
                if let text = String(data: data, encoding: .utf8) {
                    print(text)
                }
            } catch {
                fputs("Jarvis window self-test failed to encode snapshot: \(error)\n", stderr)
                Foundation.exit(1)
            }
            let windowCount = finalSnapshot["window_count"] as? Int ?? 0
            let panelVisible = finalSnapshot["panel_is_visible"] as? Bool ?? false
            let sessionLocked = finalSnapshot["session_locked"] as? Bool ?? false
            Foundation.exit(windowCount > 0 && panelVisible && !sessionLocked ? 0 : 1)
        }

        RunLoop.main.run()
    }
}

@MainActor
final class JarvisAppDelegate: NSObject, NSApplicationDelegate, NSMenuDelegate {
    private var statusItem: NSStatusItem?
    private var statusMenu: NSMenu?
    private var speechMuteItem: NSMenuItem?
    private var wakeListenerItem: NSMenuItem?
    private var panel: NSWindow?
    private var summonWindowController: JarvisSummonWindowController?
    private let model = JarvisShellModel()
    private var hotKeyService: JarvisHotKeyService?
    private var hotKeyStatus: HotKeyRegistrationResult?
    private var statusHelperProcess: Process?
    private var shouldKeepStatusHelperRunning = false
    private var cancellables: Set<AnyCancellable> = []
    private let selfTestMode: Bool
    private static let statusHelperRestartDelayNanoseconds: UInt64 = 250_000_000
    private static let panelDefaultSize = NSSize(width: 900, height: 900)
    private static let panelMinimumSize = NSSize(width: 860, height: 860)

    init(selfTestMode: Bool = false) {
        self.selfTestMode = selfTestMode
        super.init()
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        terminateStaleJarvisProcesses()
        configureMainMenu()
        if Self.menuBarItemEnabled {
            configureStatusItem()
        }
        if !selfTestMode {
            model.onSpeechMuteStateChanged = { [weak self] in
                self?.updateSpeechMuteMenuItem()
            }
            model.onSpeechPlaybackMayStart = { [weak self] in
                self?.startStatusHelper()
            }
            model.onSpeechPlaybackLikelyStarted = { [weak self] in
                self?.startStatusHelper()
            }
            model.$summonSurface
                .receive(on: RunLoop.main)
                .sink { [weak self] surface in
                    self?.syncSummonSurface(surface)
                }
                .store(in: &cancellables)
            registerStatusHelperNotifications()
            configureHotKey()
            startStatusHelper()
            model.startWorkerMonitoring()
            model.autoStartWakeListenerIfEnabled()
            updateWakeListenerMenuItem()
            openPanelWindow(refreshModel: false)
            return
        }
        openPanelWindow(refreshModel: false)
    }

    func applicationWillTerminate(_ notification: Notification) {
        cancellables.removeAll()
        DistributedNotificationCenter.default().removeObserver(self)
        stopStatusHelper()
        model.stopWorkerMonitoring()
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        openPanel()
        return true
    }

    private func configureMainMenu() {
        let mainMenu = NSMenu()

        let appMenuItem = NSMenuItem()
        let appMenu = NSMenu(title: "Jarvis")
        let quitItem = NSMenuItem(title: "Quit Jarvis", action: #selector(quit), keyEquivalent: "q")
        quitItem.target = self
        appMenu.addItem(quitItem)
        appMenuItem.submenu = appMenu
        mainMenu.addItem(appMenuItem)

        let fileMenuItem = NSMenuItem()
        let fileMenu = NSMenu(title: "File")
        let closeItem = NSMenuItem(title: "Close Window", action: #selector(closeWindow), keyEquivalent: "w")
        closeItem.target = self
        fileMenu.addItem(closeItem)
        fileMenuItem.submenu = fileMenu
        mainMenu.addItem(fileMenuItem)

        let editMenuItem = NSMenuItem()
        let editMenu = NSMenu(title: "Edit")
        addResponderMenuItem("Undo", action: Selector(("undo:")), keyEquivalent: "z", to: editMenu)
        let redoItem = NSMenuItem(title: "Redo", action: Selector(("redo:")), keyEquivalent: "Z")
        redoItem.keyEquivalentModifierMask = [.command, .shift]
        redoItem.target = nil
        editMenu.addItem(redoItem)
        editMenu.addItem(.separator())
        addResponderMenuItem("Cut", action: #selector(NSText.cut(_:)), keyEquivalent: "x", to: editMenu)
        addResponderMenuItem("Copy", action: #selector(NSText.copy(_:)), keyEquivalent: "c", to: editMenu)
        let pasteItem = NSMenuItem(title: "Paste", action: #selector(pasteCommand), keyEquivalent: "v")
        pasteItem.target = self
        editMenu.addItem(pasteItem)
        editMenu.addItem(.separator())
        addResponderMenuItem("Select All", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a", to: editMenu)
        editMenuItem.submenu = editMenu
        mainMenu.addItem(editMenuItem)

        NSApp.mainMenu = mainMenu
    }

    private func addResponderMenuItem(
        _ title: String,
        action: Selector,
        keyEquivalent: String,
        to menu: NSMenu
    ) {
        let item = NSMenuItem(title: title, action: action, keyEquivalent: keyEquivalent)
        item.target = nil
        menu.addItem(item)
    }

    private func configureStatusItem() {
        let item = NSStatusBar.system.statusItem(withLength: Self.statusItemLength)
        let image = Self.statusItemImage()
        item.button?.title = Self.statusItemTitle
        item.button?.image = image
        item.button?.imagePosition = .imageOnly
        item.button?.toolTip = "Jarvis"
        item.button?.setAccessibilityLabel("Jarvis")
        item.button?.target = self
        item.button?.action = #selector(statusItemClicked(_:))
        item.button?.sendAction(on: [.leftMouseUp, .rightMouseUp])

        let menu = NSMenu()
        menu.delegate = self
        menu.addItem(NSMenuItem(title: "Open Panel", action: #selector(openPanel), keyEquivalent: "o"))
        menu.addItem(NSMenuItem(title: "Run Status", action: #selector(runStatus), keyEquivalent: "r"))
        menu.addItem(NSMenuItem(title: "Open Dashboard", action: #selector(openDashboard), keyEquivalent: "d"))
        menu.addItem(NSMenuItem(title: "Open Overnight Report", action: #selector(openOvernightReport), keyEquivalent: ""))
        menu.addItem(NSMenuItem(title: "Open Questions", action: #selector(openCapabilityQuestions), keyEquivalent: ""))
        menu.addItem(NSMenuItem(title: "Open Wake Test", action: #selector(openWakeTest), keyEquivalent: ""))
        menu.addItem(NSMenuItem(title: "Shortcut: Command+Option+J", action: #selector(showHotKeyStatus), keyEquivalent: ""))
        let wakeItem = NSMenuItem(title: Self.wakeListenerMenuTitle(listening: model.isWakeListening), action: #selector(toggleWakeListener), keyEquivalent: "")
        wakeListenerItem = wakeItem
        menu.addItem(wakeItem)
        let muteItem = NSMenuItem(title: Self.speechMuteMenuTitle(muted: model.isSpeechMuted), action: #selector(toggleSpeechMute), keyEquivalent: "")
        speechMuteItem = muteItem
        menu.addItem(muteItem)
        menu.addItem(NSMenuItem(title: Self.musicStopMenuTitle, action: #selector(stopMusic), keyEquivalent: ""))
        menu.addItem(NSMenuItem(title: Self.audioUnmuteMenuTitle, action: #selector(unmuteAudio), keyEquivalent: ""))
        menu.addItem(.separator())
        menu.addItem(NSMenuItem(title: "Quit Jarvis", action: #selector(quit), keyEquivalent: "q"))

        for item in menu.items {
            item.target = self
        }

        statusMenu = menu
        statusItem = item
    }

    private static var menuBarItemEnabled: Bool {
        menuBarItemEnabled(environment: ProcessInfo.processInfo.environment)
    }

    static func menuBarItemEnabled(environment: [String: String]) -> Bool {
        false
    }

    static func speechMuteMenuTitle(muted: Bool) -> String {
        muted ? "Keep Blabbering" : "Shut Up"
    }

    static func wakeListenerMenuTitle(listening: Bool) -> String {
        listening ? "Stop Hey Jarvis" : "Start Hey Jarvis"
    }

    static var musicStopMenuTitle: String {
        "Stop Music"
    }

    static var audioUnmuteMenuTitle: String {
        "Unmute Audio"
    }

    static var statusItemLength: CGFloat {
        NSStatusItem.squareLength
    }

    static var statusItemTitle: String {
        ""
    }

    static var statusItemFallbackTitle: String {
        ""
    }

    func menuNeedsUpdate(_ menu: NSMenu) {
        updateWakeListenerMenuItem()
        updateSpeechMuteMenuItem()
    }

    private static func statusItemImage() -> NSImage? {
        guard let url = Bundle.main.url(forResource: "JarvisMenuHead", withExtension: "png")
            ?? Bundle.main.url(forResource: "JarvisLogo", withExtension: "png"),
              let image = NSImage(contentsOf: url) else {
            return nil
        }
        image.size = NSSize(width: 18, height: 18)
        image.isTemplate = false
        return image
    }

    @objc private func statusItemClicked(_ sender: NSStatusBarButton) {
        let event = NSApp.currentEvent
        if event?.type == .rightMouseUp || event?.modifierFlags.contains(.control) == true {
            showStatusMenu(from: sender)
            return
        }
        openPanel()
    }

    private func showStatusMenu(from sender: NSStatusBarButton? = nil) {
        guard let statusMenu else {
            openPanel()
            return
        }
        updateWakeListenerMenuItem()
        updateSpeechMuteMenuItem()
        let sourceView = sender ?? statusItem?.button
        guard let sourceView else {
            openPanel()
            return
        }
        statusMenu.popUp(positioning: nil, at: NSPoint(x: 0, y: sourceView.bounds.height + 4), in: sourceView)
    }

    private func configureHotKey() {
        let service = JarvisHotKeyService { [weak self] in
            self?.openPanel()
        }
        let result = service.start()
        hotKeyService = service
        hotKeyStatus = result
    }

    private func syncSummonSurface(_ surface: JarvisSummonSurface) {
        guard surface.isVisible else {
            summonWindowController?.hide()
            return
        }
        let controller = summonWindowController ?? JarvisSummonWindowController(model: model)
        summonWindowController = controller
        controller.show()
    }

    @objc private func openPanel() {
        openPanelWindow(refreshModel: true)
    }

    private func openPanelWindow(refreshModel: Bool) {
        if panel == nil {
            let rootView = JarvisPanelView(model: model)
            let hostingController = NSHostingController(rootView: rootView)
            let window = NSWindow(
                contentRect: NSRect(origin: .zero, size: Self.panelDefaultSize),
                styleMask: [.titled, .closable, .resizable, .miniaturizable],
                backing: .buffered,
                defer: false
            )
            window.title = "Jarvis"
            window.level = .normal
            window.contentViewController = hostingController
            window.isReleasedWhenClosed = false
            window.minSize = Self.panelMinimumSize
            window.setContentSize(Self.panelDefaultSize)
            window.center()
            panel = window
        }

        panel?.makeKeyAndOrderFront(nil)
        panel?.orderFrontRegardless()
        NSApp.activate(ignoringOtherApps: true)
        if refreshModel {
            model.refresh()
        }
    }

    @objc private func closeWindow() {
        panel?.performClose(nil)
    }

    @objc private func runStatus() {
        openPanel()
        model.submit("status")
    }

    @objc private func openDashboard() {
        NSWorkspace.shared.open(model.dashboardURL)
    }

    @objc private func openOvernightReport() {
        NSWorkspace.shared.open(model.overnightReportURL)
    }

    @objc private func openCapabilityQuestions() {
        NSWorkspace.shared.open(model.capabilityQuestionsURL)
    }

    @objc private func openWakeTest() {
        NSWorkspace.shared.open(model.wakeAuditionURL)
    }

    @objc private func toggleWakeListener() {
        model.toggleWakeListener()
        updateWakeListenerMenuItem()
    }

    @objc private func toggleSpeechMute() {
        model.toggleSpeechMuted()
        updateSpeechMuteMenuItem()
    }

    @objc private func stopMusic() {
        model.stopMusic()
    }

    @objc private func unmuteAudio() {
        model.unmuteAudio()
    }

    private func updateWakeListenerMenuItem() {
        wakeListenerItem?.title = Self.wakeListenerMenuTitle(listening: model.isWakeListening)
    }

    private func updateSpeechMuteMenuItem() {
        speechMuteItem?.title = Self.speechMuteMenuTitle(muted: model.isSpeechMuted)
    }

    @objc private func pasteCommand(_ sender: Any?) {
        if let firstResponder = panel?.firstResponder,
           firstResponder.responds(to: #selector(NSText.paste(_:))) {
            NSApp.sendAction(#selector(NSText.paste(_:)), to: firstResponder, from: sender)
            return
        }
        model.pasteFromClipboard()
    }

    @objc private func showHotKeyStatus() {
        let status = hotKeyStatus?.description ?? "Hotkey not checked"
        let alert = NSAlert()
        alert.messageText = "Jarvis Shortcut"
        alert.informativeText = status
        alert.addButton(withTitle: "OK")
        alert.runModal()
    }

    @objc private func quit() {
        NSApp.terminate(nil)
    }

    private func registerStatusHelperNotifications() {
        let center = DistributedNotificationCenter.default()
        center.addObserver(self, selector: #selector(handleStatusHelperOpenPanel), name: MainAppNotification.openPanel.name, object: nil)
        center.addObserver(self, selector: #selector(handleStatusHelperRunStatus), name: MainAppNotification.runStatus.name, object: nil)
        center.addObserver(self, selector: #selector(handleStatusHelperToggleWakeListener), name: MainAppNotification.toggleWakeListener.name, object: nil)
        center.addObserver(self, selector: #selector(handleStatusHelperStopMusic), name: MainAppNotification.stopMusic.name, object: nil)
        center.addObserver(self, selector: #selector(handleStatusHelperSpeechMuteChanged), name: MainAppNotification.speechMuteChanged.name, object: nil)
        center.addObserver(self, selector: #selector(handleStatusHelperQuit), name: MainAppNotification.quit.name, object: nil)
    }

    private func startStatusHelper() {
        shouldKeepStatusHelperRunning = true
        if statusHelperProcess?.isRunning == true {
            return
        }
        let helperURL = Bundle.main.bundleURL
            .appendingPathComponent("Contents")
            .appendingPathComponent("MacOS")
            .appendingPathComponent("jarvis-status-helper")
        guard FileManager.default.isExecutableFile(atPath: helperURL.path) else {
            ensureFallbackStatusItem()
            return
        }
        let process = Process()
        process.executableURL = helperURL
        process.arguments = [
            "--app-bundle-path",
            Bundle.main.bundlePath,
            "--base-url",
            model.dashboardURL.absoluteString,
            "--parent-pid",
            String(ProcessInfo.processInfo.processIdentifier),
        ]
        process.terminationHandler = { [weak self] terminatedProcess in
            Task { @MainActor in
                if self?.statusHelperProcess === terminatedProcess {
                    self?.statusHelperProcess = nil
                    if self?.shouldKeepStatusHelperRunning == true {
                        Task { @MainActor in
                            try? await Task.sleep(nanoseconds: Self.statusHelperRestartDelayNanoseconds)
                            if self?.shouldKeepStatusHelperRunning == true {
                                self?.startStatusHelper()
                            }
                        }
                    }
                }
            }
        }
        do {
            try process.run()
            removeFallbackStatusItemIfNeeded()
            statusHelperProcess = process
        } catch {
            statusHelperProcess = nil
            ensureFallbackStatusItem()
        }
    }

    private func ensureFallbackStatusItem() {
        guard statusItem == nil else {
            return
        }
        configureStatusItem()
    }

    private func removeFallbackStatusItemIfNeeded() {
        guard !Self.menuBarItemEnabled, let statusItem else {
            return
        }
        NSStatusBar.system.removeStatusItem(statusItem)
        self.statusItem = nil
        statusMenu = nil
        speechMuteItem = nil
        wakeListenerItem = nil
    }

    private func terminateStaleJarvisProcesses() {
        let snapshot = Self.processSnapshot()
        let currentPID = ProcessInfo.processInfo.processIdentifier
        let pids = Self.staleJarvisProcessIDs(
            from: snapshot,
            currentPID: currentPID,
            currentBundlePath: Bundle.main.bundlePath
        )
        for pid in pids {
            Darwin.kill(pid, SIGTERM)
        }
    }

    private static func processSnapshot() -> String {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/pgrep")
        process.arguments = ["-fl", "jarvis-menu-bar|jarvis-status-helper"]
        let pipe = Pipe()
        process.standardOutput = pipe
        process.standardError = Pipe()
        do {
            try process.run()
        } catch {
            return ""
        }
        let deadline = Date().addingTimeInterval(0.8)
        while process.isRunning && Date() < deadline {
            Thread.sleep(forTimeInterval: 0.02)
        }
        if process.isRunning {
            process.terminate()
            return ""
        }
        let data = pipe.fileHandleForReading.readDataToEndOfFile()
        return String(data: data, encoding: .utf8) ?? ""
    }

    static func staleJarvisProcessIDs(
        from psOutput: String,
        currentPID: pid_t,
        currentBundlePath: String
    ) -> [pid_t] {
        let currentBundleMarker = "\(currentBundlePath)/Contents/MacOS/"
        return psOutput
            .split(separator: "\n")
            .compactMap { rawLine -> pid_t? in
                let line = rawLine.trimmingCharacters(in: .whitespaces)
                let fields = line.split(separator: " ", maxSplits: 2, omittingEmptySubsequences: true)
                guard fields.count >= 2,
                      let pid = pid_t(String(fields[0])),
                      pid != currentPID else {
                    return nil
                }
                let parentPID: pid_t?
                let command: String
                if fields.count == 3, let parsedParentPID = pid_t(String(fields[1])) {
                    parentPID = parsedParentPID
                    command = String(fields[2])
                } else {
                    parentPID = nil
                    command = fields.dropFirst().map(String.init).joined(separator: " ")
                }
                if command.contains(".app/Contents/MacOS/jarvis-menu-bar") {
                    return pid
                }
                if command.contains(".app/Contents/MacOS/jarvis-status-helper"),
                   parentPID != currentPID || !command.contains(currentBundleMarker) {
                    return pid
                }
                return nil
            }
    }

    private func stopStatusHelper() {
        shouldKeepStatusHelperRunning = false
        guard let process = statusHelperProcess else {
            return
        }
        if process.isRunning {
            process.terminate()
        }
        statusHelperProcess = nil
    }

    @objc private func handleStatusHelperOpenPanel(_ notification: Notification) {
        openPanel()
    }

    @objc private func handleStatusHelperRunStatus(_ notification: Notification) {
        runStatus()
    }

    @objc private func handleStatusHelperToggleWakeListener(_ notification: Notification) {
        toggleWakeListener()
    }

    @objc private func handleStatusHelperSpeechMuteChanged(_ notification: Notification) {
        Task {
            await model.refreshSpeechMuteStatusNow()
            updateSpeechMuteMenuItem()
        }
    }

    @objc private func handleStatusHelperStopMusic(_ notification: Notification) {
        model.stopMusic()
    }

    @objc private func handleStatusHelperQuit(_ notification: Notification) {
        quit()
    }

    fileprivate func debugOpenPanelForSelfTest() {
        openPanelWindow(refreshModel: false)
    }

    fileprivate func debugStartStatusHelperForSelfTest() {
        startStatusHelper()
    }

    fileprivate func debugRefreshModelForSelfTest() {
        model.refresh()
    }

    fileprivate func debugWindowSnapshot(label: String) -> [String: Any] {
        let windows = NSApp.windows
        return [
            "activation_policy": NSApp.activationPolicy().rawValue,
            "is_active": NSApp.isActive,
            "label": label,
            "panel_exists": panel != nil,
            "panel_is_visible": panel?.isVisible ?? false,
            "panel_title": panel?.title ?? "",
            "session_locked": Self.sessionScreenIsLocked(),
            "window_count": windows.count,
            "window_titles": windows.map(\.title),
            "window_visibility": windows.map(\.isVisible),
        ]
    }

    private static func sessionScreenIsLocked() -> Bool {
        guard let info = CGSessionCopyCurrentDictionary() as? [String: Any] else {
            return false
        }
        if let locked = info["CGSSessionScreenIsLocked"] as? Bool {
            return locked
        }
        if let lockedNumber = info["CGSSessionScreenIsLocked"] as? NSNumber {
            return lockedNumber.intValue != 0
        }
        return false
    }
}

private enum MainAppNotification: String {
    case openPanel = "statusHelper.openPanel"
    case runStatus = "statusHelper.runStatus"
    case toggleWakeListener = "statusHelper.toggleWakeListener"
    case stopMusic = "statusHelper.stopMusic"
    case speechMuteChanged = "statusHelper.speechMuteChanged"
    case quit = "statusHelper.quit"

    // SYNC WITH: JarvisStatusHelper/main.swift, which keeps its OWN identical copy
    // of this enum. The status helper and this main app are two separate
    // executable targets, so neither can import the other's private enum -- the
    // duplication is deliberate. The two copies MUST stay identical: same case
    // rawValues, same `fallbackBundleIdentifier` literal, and same `name`
    // computation. If they diverge, the two processes derive different
    // DistributedNotificationCenter names and silently stop talking to each other.
    // Nothing verifies this match across the process boundary at build or run time
    // (the helper's --self-test only checks its own internal self-consistency plus
    // the pinned fallback literal), so any edit here MUST be mirrored by hand in
    // JarvisStatusHelper/main.swift's copy, and vice versa.
    //
    // Keep the legacy bundle id as the fallback so `swift run` (no bundle, nil
    // bundleIdentifier) and the default `local.leo.jarvis` build produce the exact
    // same notification names they did before, while a rebranded BUNDLE_ID keeps the
    // main app and the separate status-helper process routed to matching names.
    //
    // IMPORTANT: matching JarvisStatusHelper/main.swift's copy of this enum relies
    // on the helper binary staying inside this app's own Contents/MacOS/ (see
    // startStatusHelper() below and build_app_bundle.sh) so its `Bundle.main`
    // resolves to this same app and reports the same CFBundleIdentifier. Moving the
    // helper out of Contents/MacOS/ would silently break every notification below
    // with no compile error and no test catching it.
    private static let fallbackBundleIdentifier = "local.leo.jarvis"

    var name: Notification.Name {
        let prefix = Bundle.main.bundleIdentifier ?? Self.fallbackBundleIdentifier
        return Notification.Name("\(prefix).\(rawValue)")
    }
}
