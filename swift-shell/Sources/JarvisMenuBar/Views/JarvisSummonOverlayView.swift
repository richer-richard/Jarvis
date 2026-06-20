import AppKit
import SwiftUI

struct JarvisSummonOverlayView: View {
    @ObservedObject var model: JarvisShellModel
    static let panelSize = CGSize(width: 300, height: 82)
    private let panelWidth: CGFloat = Self.panelSize.width
    private let panelHeight: CGFloat = Self.panelSize.height

    var body: some View {
        let surface = model.summonSurface
        ZStack {
            JarvisGlassCapsule(accent: accentColor(for: surface.phase))
                .overlay(
                    Capsule(style: .continuous)
                        .strokeBorder(borderGradient(for: surface.phase), lineWidth: 0.7)
                )

            HStack(spacing: 11) {
                JarvisSummonCore(phase: surface.phase)
                    .frame(width: 38, height: 38)

                VStack(alignment: .leading, spacing: 3) {
                    HStack(alignment: .firstTextBaseline, spacing: 8) {
                        Text(surface.title.isEmpty ? phaseTitle(surface.phase) : surface.title)
                            .font(.system(size: 15, weight: .semibold, design: .rounded))
                            .foregroundStyle(.white)
                            .lineLimit(1)
                            .minimumScaleFactor(0.72)
                            .shadow(color: .black.opacity(0.24), radius: 2, x: 0, y: 1)

                        Spacer(minLength: 6)

                        Text(phaseLabel(surface.phase))
                            .font(.system(size: 7.5, weight: .bold, design: .rounded))
                            .tracking(0.7)
                            .foregroundStyle(accentColor(for: surface.phase))
                            .padding(.horizontal, 6)
                            .padding(.vertical, 3)
                            .background(Color.black.opacity(0.22), in: Capsule(style: .continuous))
                    }

                    if !surface.transcript.isEmpty {
                        Text(surface.transcript)
                            .font(.system(size: 10.5, weight: .medium, design: .rounded))
                            .foregroundStyle(.white.opacity(0.72))
                            .lineLimit(1)
                            .transition(.opacity.combined(with: .move(edge: .top)))
                    }

                    if !surface.response.isEmpty {
                        Text(surface.response)
                            .font(.system(size: 12.5, weight: .semibold, design: .rounded))
                            .foregroundStyle(.white)
                            .lineLimit(2)
                            .shadow(color: .black.opacity(0.22), radius: 2, x: 0, y: 1)
                            .transition(.opacity.combined(with: .move(edge: .bottom)))
                    } else {
                        Text(surface.detail.isEmpty ? phaseDetail(surface.phase) : surface.detail)
                            .font(.system(size: 10.5, weight: .medium, design: .rounded))
                            .foregroundStyle(.white.opacity(0.72))
                            .lineLimit(1)
                    }
                }
            }
            .padding(.horizontal, 13)
            .padding(.vertical, 11)
        }
        .frame(width: panelWidth, height: panelHeight)
        .clipShape(Capsule(style: .continuous))
        .contentShape(Capsule(style: .continuous))
        .compositingGroup()
        .shadow(color: Color.black.opacity(0.24), radius: 18, x: 0, y: 9)
        .shadow(color: accentColor(for: surface.phase).opacity(0.16), radius: 18, x: 0, y: 5)
        .background(Color.clear)
        .animation(.spring(response: 0.34, dampingFraction: 0.86), value: surface)
    }

    private func phaseTitle(_ phase: JarvisSummonPhase) -> String {
        switch phase {
        case .hidden:
            return ""
        case .listening:
            return "Listening."
        case .transcribing:
            return "I heard you."
        case .thinking:
            return "Working on it."
        case .answering:
            return "Answering."
        case .speaking:
            return "Speaking."
        case .complete:
            return "Done."
        case .error:
            return "Something went wrong."
        }
    }

    private func phaseDetail(_ phase: JarvisSummonPhase) -> String {
        switch phase {
        case .hidden:
            return ""
        case .listening:
            return "Listening for your command."
        case .transcribing:
            return "Cleaning up the dictation."
        case .thinking:
            return "Finding the best way to help."
        case .answering:
            return "Preparing the answer."
        case .speaking:
            return "Reading the answer aloud."
        case .complete:
            return "Ready for the next command."
        case .error:
            return "Check the Jarvis window for details."
        }
    }

    private func phaseLabel(_ phase: JarvisSummonPhase) -> String {
        switch phase {
        case .hidden:
            return ""
        case .listening:
            return "LISTEN"
        case .transcribing:
            return "HEARD"
        case .thinking:
            return "THINK"
        case .answering:
            return "ANSWER"
        case .speaking:
            return "SPEAK"
        case .complete:
            return "DONE"
        case .error:
            return "ERROR"
        }
    }

    private func accentColor(for phase: JarvisSummonPhase) -> Color {
        switch phase {
        case .error:
            return Color(red: 1.0, green: 0.32, blue: 0.27)
        case .speaking, .complete:
            return Color(red: 0.18, green: 0.86, blue: 0.74)
        case .answering:
            return Color(red: 0.72, green: 0.52, blue: 1.0)
        case .thinking, .transcribing:
            return Color(red: 0.30, green: 0.67, blue: 1.0)
        default:
            return Color(red: 0.98, green: 0.70, blue: 0.25)
        }
    }

    private func borderGradient(for phase: JarvisSummonPhase) -> LinearGradient {
        LinearGradient(
            colors: [
                Color.white.opacity(0.46),
                accentColor(for: phase).opacity(0.64),
                Color.white.opacity(0.18),
            ],
            startPoint: .topLeading,
            endPoint: .bottomTrailing
        )
    }
}

private struct JarvisGlassCapsule: View {
    let accent: Color

    var body: some View {
        ZStack {
            if #available(macOS 26.0, *) {
                Capsule(style: .continuous)
                    .fill(Color.white.opacity(0.001))
                    .glassEffect(.regular.tint(accent.opacity(0.18)), in: Capsule(style: .continuous))
            } else {
                JarvisVisualEffectBackground()
                    .background(Color.clear)
                    .clipShape(Capsule(style: .continuous))
            }

            Capsule(style: .continuous)
                .fill(
                    LinearGradient(
                        colors: [
                            Color.white.opacity(0.22),
                            Color.white.opacity(0.07),
                            accent.opacity(0.10),
                        ],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )
                .blendMode(.plusLighter)

            Capsule(style: .continuous)
                .fill(
                    RadialGradient(
                        colors: [
                            accent.opacity(0.20),
                            Color.clear,
                        ],
                        center: .bottomTrailing,
                        startRadius: 12,
                        endRadius: 220
                    )
                )
        }
    }
}

private struct JarvisVisualEffectBackground: NSViewRepresentable {
    func makeNSView(context: Context) -> NSVisualEffectView {
        let view = NSVisualEffectView()
        view.material = .hudWindow
        view.blendingMode = .behindWindow
        view.state = .active
        view.isEmphasized = true
        view.wantsLayer = true
        view.layer?.backgroundColor = NSColor.clear.cgColor
        return view
    }

    func updateNSView(_ view: NSVisualEffectView, context: Context) {
        view.material = .hudWindow
        view.blendingMode = .behindWindow
        view.state = .active
    }
}

private struct JarvisSummonCore: View {
    let phase: JarvisSummonPhase

    var body: some View {
        TimelineView(.animation) { timeline in
            let time = timeline.date.timeIntervalSinceReferenceDate
            let spin = Angle.degrees(time.truncatingRemainder(dividingBy: 3.2) / 3.2 * 360)
            let breath = 0.92 + 0.08 * sin(time * 3.4)
            let speakingLevel = phase == .speaking ? 0.55 + 0.45 * abs(sin(time * 8.0)) : 0

            ZStack {
                Circle()
                    .fill(radialFill)
                    .overlay(Circle().stroke(Color.white.opacity(0.24), lineWidth: 0.7))
                    .scaleEffect(breath)

                Circle()
                    .trim(from: 0.08, to: activeTrim)
                    .stroke(
                        AngularGradient(
                            colors: [
                                Color(red: 0.98, green: 0.70, blue: 0.25),
                                Color(red: 0.28, green: 0.72, blue: 1.0),
                                Color(red: 0.78, green: 0.52, blue: 1.0),
                                Color(red: 0.18, green: 0.86, blue: 0.74),
                                Color(red: 0.98, green: 0.70, blue: 0.25),
                            ],
                            center: .center
                        ),
                        style: StrokeStyle(lineWidth: 3.5, lineCap: .round)
                    )
                    .rotationEffect(spin)

                Circle()
                    .trim(from: 0.62, to: 0.88)
                    .stroke(Color.white.opacity(0.68), style: StrokeStyle(lineWidth: 1.4, lineCap: .round))
                    .rotationEffect(-spin * 0.72)

                if phase == .speaking {
                    JarvisSpeakingWave(time: time, level: speakingLevel)
                        .frame(width: 28, height: 20)
                        .offset(y: 14)
                        .transition(.opacity)
                }

                Image(systemName: iconName)
                    .font(.system(size: 16, weight: .semibold))
                    .symbolRenderingMode(.hierarchical)
                    .foregroundStyle(.white)
                    .shadow(color: Color.black.opacity(0.20), radius: 4, x: 0, y: 2)
            }
        }
    }

    private var radialFill: RadialGradient {
        RadialGradient(
            colors: [
                Color.white.opacity(0.88),
                Color(red: 0.36, green: 0.70, blue: 1.0).opacity(0.56),
                Color(red: 0.10, green: 0.14, blue: 0.24).opacity(0.82),
            ],
            center: .topLeading,
            startRadius: 4,
            endRadius: 46
        )
    }

    private var activeTrim: CGFloat {
        switch phase {
        case .listening:
            return 0.54
        case .transcribing:
            return 0.64
        case .thinking:
            return 0.74
        case .answering:
            return 0.84
        case .speaking:
            return 0.94
        case .complete:
            return 1.0
        case .error:
            return 0.42
        case .hidden:
            return 0.08
        }
    }

    private var iconName: String {
        switch phase {
        case .listening, .transcribing:
            return "waveform"
        case .thinking:
            return "sparkles"
        case .answering:
            return "text.bubble"
        case .speaking:
            return "speaker.wave.2.fill"
        case .complete:
            return "checkmark"
        case .error:
            return "exclamationmark"
        case .hidden:
            return "circle"
        }
    }
}

private struct JarvisSpeakingWave: View {
    let time: TimeInterval
    let level: Double

    var body: some View {
        HStack(alignment: .center, spacing: 2.4) {
            ForEach(0..<5, id: \.self) { index in
                Capsule(style: .continuous)
                    .fill(
                        LinearGradient(
                            colors: [
                                Color(red: 0.28, green: 0.72, blue: 1.0),
                                Color(red: 0.18, green: 0.86, blue: 0.74),
                                Color.white.opacity(0.86),
                            ],
                            startPoint: .bottom,
                            endPoint: .top
                        )
                    )
                    .frame(width: 3.2, height: barHeight(index))
                    .shadow(color: Color(red: 0.18, green: 0.86, blue: 0.74).opacity(0.44), radius: 4, x: 0, y: 0)
            }
        }
        .opacity(0.92)
    }

    private func barHeight(_ index: Int) -> CGFloat {
        let wave = abs(sin(time * 9.2 + Double(index) * 0.72))
        return CGFloat(6.0 + (4.0 + 14.0 * wave) * level)
    }
}
