import AppKit
import Combine
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
    private var cancellables: Set<AnyCancellable> = []

    func applicationDidFinishLaunching(_ notification: Notification) {
        model.onSpeechMuteStateChanged = { [weak self] in
            self?.updateSpeechMuteMenuItem()
        }
        model.$summonSurface
            .receive(on: RunLoop.main)
            .sink { [weak self] surface in
                self?.syncSummonSurface(surface)
            }
            .store(in: &cancellables)
        configureMainMenu()
        if Self.menuBarItemEnabled {
            configureStatusItem()
        }
        configureHotKey()
        model.startWorkerMonitoring()
        model.refresh()
        openPanel()
    }

    func applicationWillTerminate(_ notification: Notification) {
        cancellables.removeAll()
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
        let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        item.button?.title = "Jarvis"
        item.button?.image = Self.statusItemImage()
        item.button?.imagePosition = .imageLeading
        item.button?.target = self
        item.button?.action = #selector(statusItemClicked(_:))
        item.button?.sendAction(on: [.leftMouseUp, .rightMouseUp])

        let menu = NSMenu()
        menu.delegate = self
        menu.addItem(NSMenuItem(title: "Open Panel", action: #selector(openPanel), keyEquivalent: "o"))
        menu.addItem(NSMenuItem(title: "Run Status", action: #selector(runStatus), keyEquivalent: "r"))
        menu.addItem(NSMenuItem(title: "Open Dashboard", action: #selector(openDashboard), keyEquivalent: "d"))
        menu.addItem(NSMenuItem(title: "Open Overnight Report", action: #selector(openOvernightReport), keyEquivalent: ""))
        menu.addItem(NSMenuItem(title: "Open Wake Test", action: #selector(openWakeTest), keyEquivalent: ""))
        menu.addItem(NSMenuItem(title: "Shortcut: Command+Option+J", action: #selector(showHotKeyStatus), keyEquivalent: ""))
        let wakeItem = NSMenuItem(title: Self.wakeListenerMenuTitle(listening: model.isWakeListening), action: #selector(toggleWakeListener), keyEquivalent: "")
        wakeListenerItem = wakeItem
        menu.addItem(wakeItem)
        let muteItem = NSMenuItem(title: Self.speechMuteMenuTitle(muted: model.isSpeechMuted), action: #selector(toggleSpeechMute), keyEquivalent: "")
        speechMuteItem = muteItem
        menu.addItem(muteItem)
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
        if let override = JarvisMenuBarApp.environmentFlag("JARVIS_SHOW_MENU_BAR_ITEM", environment: environment) {
            return override
        }
        return true
    }

    static func speechMuteMenuTitle(muted: Bool) -> String {
        muted ? "Keep Blabbering" : "Shut Up"
    }

    static func wakeListenerMenuTitle(listening: Bool) -> String {
        listening ? "Stop Hey Jarvis" : "Start Hey Jarvis"
    }

    func menuNeedsUpdate(_ menu: NSMenu) {
        updateWakeListenerMenuItem()
        updateSpeechMuteMenuItem()
    }

    private static func statusItemImage() -> NSImage? {
        let fallback = NSImage(systemSymbolName: "bolt.horizontal.circle", accessibilityDescription: "Jarvis")
        guard let url = Bundle.main.url(forResource: "JarvisLogo", withExtension: "png"),
              let image = NSImage(contentsOf: url) else {
            return fallback
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
        if panel == nil {
            let rootView = JarvisPanelView(model: model)
            let hostingController = NSHostingController(rootView: rootView)
            let window = NSWindow(
                contentRect: NSRect(x: 0, y: 0, width: 680, height: 720),
                styleMask: [.titled, .closable, .resizable, .miniaturizable],
                backing: .buffered,
                defer: false
            )
            window.title = "Jarvis"
            window.level = .normal
            window.contentViewController = hostingController
            window.isReleasedWhenClosed = false
            window.center()
            panel = window
        }

        panel?.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        model.refresh()
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
}
