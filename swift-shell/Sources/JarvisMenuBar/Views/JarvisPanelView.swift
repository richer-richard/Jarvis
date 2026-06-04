import AppKit
import JarvisClient
import SwiftUI

struct JarvisPanelView: View {
    @ObservedObject var model: JarvisShellModel

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            header
            Divider()
            chatSection
            composer
            quickActions
            readinessFooter
        }
        .padding(18)
        .frame(minWidth: 640, minHeight: 680)
        .task {
            model.refresh()
        }
    }

    private var header: some View {
        HStack(alignment: .center, spacing: 12) {
            JarvisLogoView(size: 58)

            VStack(alignment: .leading, spacing: 3) {
                Text("Jarvis")
                    .font(.title2.weight(.bold))
                Text("Local assistant prototype")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }

            Spacer()

            HStack(spacing: 7) {
                StatusChip(label: model.modeText)
                StatusChip(label: model.state)
                StatusChip(label: model.connection)
            }
        }
    }

    private var chatSection: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 10) {
                    ForEach(model.messages) { message in
                        ChatBubble(message: message)
                            .id(message.id)
                    }
                }
                .padding(.vertical, 6)
            }
            .frame(minHeight: 340)
            .onChange(of: model.messages.count) { _, _ in
                guard let last = model.messages.last else {
                    return
                }
                withAnimation(.easeOut(duration: 0.18)) {
                    proxy.scrollTo(last.id, anchor: .bottom)
                }
            }
        }
        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 8))
    }

    private var composer: some View {
        HStack(spacing: 10) {
            PasteFriendlyCommandField(
                text: $model.command,
                placeholder: "Type to Jarvis...",
                isEnabled: !model.isBusy && !model.isPaused
            ) {
                model.submitCurrentCommand()
            }
            .frame(height: 28)

            Button("Paste") {
                model.pasteFromClipboard()
            }
            .disabled(model.isBusy || model.isPaused)
            .help("Paste clipboard text into the Jarvis command field.")

            Button(model.isBusy ? "Thinking" : "Send") {
                model.submitCurrentCommand()
            }
            .keyboardShortcut(.return, modifiers: .command)
            .disabled(model.isBusy || model.isPaused)
        }
    }

    private var quickActions: some View {
        HStack(spacing: 8) {
            QuickActionButton("Email", command: "check my email", model: model)
            QuickActionButton("Status", command: "status", model: model)
            QuickActionButton("Wake Test", command: "wake: Hey Jarvis status", model: model)
            QuickActionButton("Screen", command: "screenshot capability", model: model)
            QuickActionButton("Codex", command: "ask Codex to review this project", model: model)
        }
    }

    private var readinessFooter: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .center, spacing: 8) {
                Button(model.isPaused ? "Resume" : "Pause") {
                    model.togglePause()
                }
                .disabled(model.isBusy)

                Button("Refresh") {
                    model.refresh()
                }

                Button("Copy Chat JSON") {
                    model.copyChatHistoryJSON()
                }
                .disabled(model.messages.isEmpty)
                .help("Copy the current Jarvis chat transcript as JSON.")

                Button("Copy Tests") {
                    model.copySmokeTestPrompts()
                }
                .help("Copy the current Jarvis smoke-test prompts.")

                Text(model.chatExportText)
                    .lineLimit(1)
                    .truncationMode(.tail)
                    .frame(maxWidth: 140, alignment: .leading)

                Spacer()

                StatusChip(label: model.permissionText)
            }

            HStack(alignment: .top, spacing: 12) {
                FooterColumn(title: "Worker", value: model.workerText)
                FooterColumn(title: "Audit", value: model.auditText)
                FooterColumn(title: "Verification", value: model.verificationText)
            }

            LazyVGrid(
                columns: [GridItem(.adaptive(minimum: 118), spacing: 8)],
                alignment: .leading,
                spacing: 8
            ) {
                ForEach(model.permissions) { permission in
                    PermissionReadinessTile(permission: permission)
                }
            }
        }
        .font(.caption)
        .foregroundStyle(.secondary)
    }
}

private struct PasteFriendlyCommandField: NSViewRepresentable {
    @Binding var text: String
    let placeholder: String
    let isEnabled: Bool
    let onSubmit: () -> Void

    func makeCoordinator() -> Coordinator {
        Coordinator(parent: self)
    }

    func makeNSView(context: Context) -> NSTextField {
        let field = NSTextField()
        field.delegate = context.coordinator
        field.target = context.coordinator
        field.action = #selector(Coordinator.submit)
        field.placeholderString = placeholder
        field.isEditable = true
        field.isSelectable = true
        field.isEnabled = isEnabled
        field.isBordered = true
        field.isBezeled = true
        field.bezelStyle = .roundedBezel
        field.usesSingleLineMode = true
        field.lineBreakMode = .byTruncatingTail
        field.focusRingType = .default
        field.font = .systemFont(ofSize: NSFont.systemFontSize)
        field.cell?.wraps = false
        field.cell?.isScrollable = true
        return field
    }

    func updateNSView(_ field: NSTextField, context: Context) {
        context.coordinator.parent = self
        if field.stringValue != text {
            field.stringValue = text
        }
        field.placeholderString = placeholder
        field.isEnabled = isEnabled
    }

    @MainActor
    final class Coordinator: NSObject, NSTextFieldDelegate {
        var parent: PasteFriendlyCommandField

        init(parent: PasteFriendlyCommandField) {
            self.parent = parent
        }

        func controlTextDidChange(_ notification: Notification) {
            guard let field = notification.object as? NSTextField else {
                return
            }
            parent.text = field.stringValue
        }

        func control(
            _ control: NSControl,
            textView: NSTextView,
            doCommandBy commandSelector: Selector
        ) -> Bool {
            if commandSelector == #selector(NSResponder.insertNewline(_:)) {
                parent.text = textView.string
                parent.onSubmit()
                return true
            }
            return false
        }

        @objc func submit(_ sender: NSTextField) {
            parent.text = sender.stringValue
            parent.onSubmit()
        }
    }
}

private struct JarvisLogoView: View {
    let size: CGFloat

    var body: some View {
        Group {
            if let image = JarvisLogoLoader.image {
                Image(nsImage: image)
                    .resizable()
                    .scaledToFill()
            } else {
                Image(systemName: "bolt.horizontal.circle.fill")
                    .resizable()
                    .scaledToFit()
                    .padding(8)
                    .foregroundStyle(.cyan)
            }
        }
        .frame(width: size, height: size)
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(.white.opacity(0.45), lineWidth: 1)
        )
        .shadow(color: .cyan.opacity(0.18), radius: 10, x: 0, y: 4)
        .accessibilityLabel("Jarvis logo")
    }
}

private enum JarvisLogoLoader {
    static var image: NSImage? {
        guard let url = Bundle.main.url(forResource: "JarvisLogo", withExtension: "png") else {
            return nil
        }
        return NSImage(contentsOf: url)
    }
}

private struct ChatBubble: View {
    let message: ChatMessage

    private var isUser: Bool {
        message.role == .user
    }

    private var title: String {
        switch message.role {
        case .user:
            return "You"
        case .jarvis:
            return "Jarvis"
        case .system:
            return "System"
        }
    }

    var body: some View {
        HStack(alignment: .top) {
            if isUser {
                Spacer(minLength: 80)
            }

            VStack(alignment: .leading, spacing: 5) {
                Text(title)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(isUser ? .white.opacity(0.82) : .secondary)
                Text(message.text)
                    .font(.body)
                    .lineSpacing(3)
                    .textSelection(.enabled)
                if let detail = message.detail, !detail.isEmpty {
                    Text(detail)
                        .font(.caption)
                        .foregroundStyle(isUser ? .white.opacity(0.7) : .secondary)
                        .lineLimit(2)
                }
            }
            .padding(.horizontal, 13)
            .padding(.vertical, 10)
            .frame(maxWidth: 440, alignment: .leading)
            .background(bubbleBackground, in: RoundedRectangle(cornerRadius: 8))
            .foregroundStyle(isUser ? .white : .primary)

            if !isUser {
                Spacer(minLength: 80)
            }
        }
        .padding(.horizontal, 10)
    }

    private var bubbleBackground: some ShapeStyle {
        isUser ? AnyShapeStyle(Color.accentColor) : AnyShapeStyle(.regularMaterial)
    }
}

private struct QuickActionButton: View {
    let title: String
    let command: String
    let model: JarvisShellModel

    init(_ title: String, command: String, model: JarvisShellModel) {
        self.title = title
        self.command = command
        self.model = model
    }

    var body: some View {
        Button(title) {
            model.command = command
            model.submit(command)
        }
        .frame(maxWidth: .infinity)
        .disabled(model.isBusy || model.isPaused)
    }
}

private struct StatusChip: View {
    let label: String

    var body: some View {
        Text(label)
            .font(.caption.monospaced())
            .lineLimit(1)
            .truncationMode(.middle)
            .padding(.horizontal, 9)
            .padding(.vertical, 5)
            .background(.thinMaterial, in: Capsule())
    }
}

private struct FooterColumn: View {
    let title: String
    let value: String

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(title)
                .font(.caption.weight(.semibold))
            Text(value)
                .lineLimit(2)
                .minimumScaleFactor(0.85)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

private struct PermissionReadinessTile: View {
    let permission: PermissionReadiness

    var body: some View {
        HStack(spacing: 7) {
            Circle()
                .fill(permission.isReady ? Color.green : Color.orange)
                .frame(width: 7, height: 7)
            VStack(alignment: .leading, spacing: 1) {
                Text(permission.label)
                    .font(.caption.weight(.semibold))
                    .lineLimit(1)
                    .truncationMode(.tail)
                Text(permission.state)
                    .font(.caption2.monospaced())
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .minimumScaleFactor(0.85)
            }
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 9)
        .padding(.vertical, 8)
        .frame(minHeight: 44)
        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 8))
        .help(permission.detail)
    }
}
