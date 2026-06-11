import Foundation

enum JarvisSummonPhase: String, Equatable {
    case hidden
    case listening
    case transcribing
    case thinking
    case answering
    case speaking
    case complete
    case error
}

struct JarvisSummonSurface: Equatable {
    var phase: JarvisSummonPhase
    var title: String
    var transcript: String
    var response: String
    var detail: String

    var isVisible: Bool {
        phase != .hidden
    }

    static let hidden = JarvisSummonSurface(
        phase: .hidden,
        title: "",
        transcript: "",
        response: "",
        detail: ""
    )
}
