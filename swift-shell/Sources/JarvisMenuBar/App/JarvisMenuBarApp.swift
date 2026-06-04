import AppKit
import Foundation
import JarvisClient
import SwiftUI

@main
struct JarvisMenuBarApp {
    static func main() {
        if CommandLine.arguments.contains("--hotkey-self-test") {
            runHotKeySelfTest()
            return
        }
        if CommandLine.arguments.contains("--permission-self-test") {
            runPermissionSelfTest()
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
        app.setActivationPolicy(.regular)
        app.run()
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
final class JarvisAppDelegate: NSObject, NSApplicationDelegate {
    private var statusItem: NSStatusItem?
    private var panel: NSWindow?
    private let model = JarvisShellModel()
    private var hotKeyService: JarvisHotKeyService?
    private var hotKeyStatus: HotKeyRegistrationResult?

    func applicationDidFinishLaunching(_ notification: Notification) {
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

        let menu = NSMenu()
        menu.addItem(NSMenuItem(title: "Open Panel", action: #selector(openPanel), keyEquivalent: "o"))
        menu.addItem(NSMenuItem(title: "Run Status", action: #selector(runStatus), keyEquivalent: "r"))
        menu.addItem(NSMenuItem(title: "Open Dashboard", action: #selector(openDashboard), keyEquivalent: "d"))
        menu.addItem(NSMenuItem(title: "Shortcut: Command+Option+J", action: #selector(showHotKeyStatus), keyEquivalent: ""))
        menu.addItem(.separator())
        menu.addItem(NSMenuItem(title: "Quit Jarvis", action: #selector(quit), keyEquivalent: "q"))

        for item in menu.items {
            item.target = self
        }

        item.menu = menu
        statusItem = item
    }

    private static var menuBarItemEnabled: Bool {
        let value = ProcessInfo.processInfo.environment["JARVIS_SHOW_MENU_BAR_ITEM"]?.lowercased()
        return ["1", "true", "yes", "on"].contains(value)
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

    private func configureHotKey() {
        let service = JarvisHotKeyService { [weak self] in
            self?.openPanel()
        }
        let result = service.start()
        hotKeyService = service
        hotKeyStatus = result
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
            window.contentViewController = hostingController
            window.isReleasedWhenClosed = false
            window.center()
            panel = window
        }

        panel?.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        model.refresh()
    }

    @objc private func runStatus() {
        openPanel()
        model.submit("status")
    }

    @objc private func openDashboard() {
        NSWorkspace.shared.open(model.dashboardURL)
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
