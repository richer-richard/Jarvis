import AppKit
import QuartzCore
import SwiftUI

@MainActor
final class JarvisSummonWindowController {
    private let window: NSPanel
    private let size = NSSize(width: 468, height: 168)
    private let edgeInset: CGFloat = 22

    init(model: JarvisShellModel) {
        let hostingController = NSHostingController(rootView: JarvisSummonOverlayView(model: model))
        let panel = NSPanel(
            contentRect: NSRect(origin: .zero, size: size),
            styleMask: [.borderless, .nonactivatingPanel],
            backing: .buffered,
            defer: false
        )
        panel.contentViewController = hostingController
        panel.backgroundColor = .clear
        panel.isOpaque = false
        panel.hasShadow = false
        panel.level = .statusBar
        panel.hidesOnDeactivate = false
        panel.isReleasedWhenClosed = false
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .transient, .ignoresCycle]
        panel.animationBehavior = .utilityWindow
        panel.ignoresMouseEvents = true
        window = panel
    }

    func show() {
        positionTopRight()
        guard !window.isVisible else {
            return
        }
        window.alphaValue = 0
        window.orderFrontRegardless()
        NSAnimationContext.runAnimationGroup { context in
            context.duration = 0.18
            context.timingFunction = CAMediaTimingFunction(name: .easeOut)
            window.animator().alphaValue = 1
        }
    }

    func hide() {
        guard window.isVisible else {
            return
        }
        NSAnimationContext.runAnimationGroup { context in
            context.duration = 0.16
            context.timingFunction = CAMediaTimingFunction(name: .easeIn)
            window.animator().alphaValue = 0
        } completionHandler: {
            Task { @MainActor in
                self.window.orderOut(nil)
                self.window.alphaValue = 1
            }
        }
    }

    private func positionTopRight() {
        let screen = NSScreen.main ?? NSScreen.screens.first
        guard let visibleFrame = screen?.visibleFrame else {
            window.setFrame(NSRect(origin: .zero, size: size), display: true)
            return
        }
        let origin = NSPoint(
            x: visibleFrame.maxX - size.width - edgeInset,
            y: visibleFrame.maxY - size.height - edgeInset
        )
        window.setFrame(NSRect(origin: origin, size: size), display: true)
    }
}
