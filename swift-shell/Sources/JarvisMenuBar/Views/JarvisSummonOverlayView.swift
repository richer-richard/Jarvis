import SwiftUI

struct JarvisSummonOverlayView: View {
    @ObservedObject var model: JarvisShellModel

    var body: some View {
        let surface = model.summonSurface
        ZStack {
            Capsule(style: .continuous)
                .fill(.ultraThinMaterial)
                .overlay(
                    Capsule(style: .continuous)
                        .strokeBorder(borderGradient(for: surface.phase), lineWidth: 1.1)
                )
                .shadow(color: Color.black.opacity(0.28), radius: 28, x: 0, y: 18)
                .shadow(color: accentColor(for: surface.phase).opacity(0.22), radius: 34, x: 0, y: 8)

            HStack(spacing: 18) {
                JarvisSummonCore(phase: surface.phase)
                    .frame(width: 72, height: 72)

                VStack(alignment: .leading, spacing: 7) {
                    HStack(alignment: .firstTextBaseline, spacing: 8) {
                        Text(surface.title.isEmpty ? phaseTitle(surface.phase) : surface.title)
                            .font(.system(size: 21, weight: .semibold, design: .rounded))
                            .foregroundStyle(.primary)
                            .lineLimit(1)
                            .minimumScaleFactor(0.72)

                        Spacer(minLength: 6)

                        Text(phaseLabel(surface.phase))
                            .font(.system(size: 10, weight: .bold, design: .rounded))
                            .tracking(0.8)
                            .foregroundStyle(accentColor(for: surface.phase))
                            .padding(.horizontal, 9)
                            .padding(.vertical, 5)
                            .background(.thinMaterial, in: Capsule(style: .continuous))
                    }

                    if !surface.transcript.isEmpty {
                        Text(surface.transcript)
                            .font(.system(size: 14, weight: .medium, design: .rounded))
                            .foregroundStyle(.secondary)
                            .lineLimit(2)
                            .transition(.opacity.combined(with: .move(edge: .top)))
                    }

                    if !surface.response.isEmpty {
                        Text(surface.response)
                            .font(.system(size: 15, weight: .semibold, design: .rounded))
                            .foregroundStyle(.primary)
                            .lineLimit(4)
                            .transition(.opacity.combined(with: .move(edge: .bottom)))
                    } else {
                        Text(surface.detail.isEmpty ? phaseDetail(surface.phase) : surface.detail)
                            .font(.system(size: 13, weight: .medium, design: .rounded))
                            .foregroundStyle(.secondary)
                            .lineLimit(2)
                    }
                }
            }
            .padding(.horizontal, 22)
            .padding(.vertical, 18)
        }
        .frame(width: 468, height: 168)
        .overlay(alignment: .bottomTrailing) {
            Capsule(style: .continuous)
                .fill(accentColor(for: surface.phase).opacity(0.34))
                .frame(width: phaseProgressWidth(surface.phase), height: 3)
                .padding(.trailing, 34)
                .padding(.bottom, 14)
                .animation(.spring(response: 0.42, dampingFraction: 0.82), value: surface.phase)
        }
        .compositingGroup()
        .animation(.spring(response: 0.34, dampingFraction: 0.86), value: surface)
    }

    private func phaseTitle(_ phase: JarvisSummonPhase) -> String {
        switch phase {
        case .hidden:
            return ""
        case .listening:
            return "Yes sir?"
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
            return "Choosing the best route."
        case .answering:
            return "Writing the response."
        case .speaking:
            return "Reading the answer aloud."
        case .complete:
            return "Ready for the next command."
        case .error:
            return "The debug window has details."
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

    private func phaseProgressWidth(_ phase: JarvisSummonPhase) -> CGFloat {
        switch phase {
        case .hidden:
            return 0
        case .listening:
            return 42
        case .transcribing:
            return 86
        case .thinking:
            return 132
        case .answering:
            return 182
        case .speaking:
            return 228
        case .complete:
            return 260
        case .error:
            return 148
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

private struct JarvisSummonCore: View {
    let phase: JarvisSummonPhase

    var body: some View {
        TimelineView(.animation) { timeline in
            let time = timeline.date.timeIntervalSinceReferenceDate
            let spin = Angle.degrees(time.truncatingRemainder(dividingBy: 3.2) / 3.2 * 360)
            let breath = 0.92 + 0.08 * sin(time * 3.4)

            ZStack {
                Circle()
                    .fill(radialFill)
                    .overlay(Circle().stroke(Color.white.opacity(0.30), lineWidth: 1))
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
                        style: StrokeStyle(lineWidth: 5.5, lineCap: .round)
                    )
                    .rotationEffect(spin)

                Circle()
                    .trim(from: 0.62, to: 0.88)
                    .stroke(Color.white.opacity(0.72), style: StrokeStyle(lineWidth: 2.2, lineCap: .round))
                    .rotationEffect(-spin * 0.72)

                Image(systemName: iconName)
                    .font(.system(size: 24, weight: .semibold))
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
