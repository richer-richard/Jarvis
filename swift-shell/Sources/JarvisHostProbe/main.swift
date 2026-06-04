import Foundation
import JarvisClient

@main
struct JarvisHostProbe {
    static func main() async {
        let arguments = Array(CommandLine.arguments.dropFirst())

        do {
            if arguments.first == "--help" || arguments.first == "-h" {
                printUsage()
                return
            }
            let client = try JarvisClient.fromEnvironment()
            if arguments.first == "--health" {
                try await printHealth(client: client)
                return
            }
            if arguments.first == "--audit-status" {
                try await printAuditStatus(client: client)
                return
            }
            if arguments.first == "--readiness" {
                try await printReadiness(client: client)
                return
            }
            if arguments.first == "--preflight" {
                try await printPreflight(client: client)
                return
            }
            if arguments.first == "--plan" {
                let command = Array(arguments.dropFirst()).isEmpty ? "status" : Array(arguments.dropFirst()).joined(separator: " ")
                try await printPlan(client: client, command: command)
                return
            }
            if arguments.first == "--mode" {
                try await printMode(client: client)
                return
            }
            if arguments.first == "--pause" {
                let reason = Array(arguments.dropFirst()).joined(separator: " ")
                let mode = try await client.setPaused(true, reason: reason.isEmpty ? "Host probe pause." : reason)
                printMode(mode)
                return
            }
            if arguments.first == "--resume" {
                let mode = try await client.setPaused(false, reason: "Host probe resume.")
                printMode(mode)
                return
            }

            let command = arguments.isEmpty ? "status" : arguments.joined(separator: " ")
            let response = try await client.send(command: command)
            print("Jarvis worker responded")
            print("Command: \(response.command ?? command)")
            print("Tool: \(response.tool ?? "unknown")")
            print("Executed: \(response.executed.map(String.init) ?? "unknown")")
            print("Summary: \(response.summary ?? "No summary")")
            if let confirmation = response.confirmation, confirmation.required {
                print("Confirmation: \(confirmation.title) [\(confirmation.kind)]")
                if let phrase = confirmation.exactPhrase {
                    print("Exact phrase: \(phrase)")
                }
            }
        } catch {
            fputs("Jarvis host probe failed: \(error)\n", stderr)
            Foundation.exit(1)
        }
    }

    private static func printUsage() {
        print("Jarvis host probe")
        print("Usage:")
        print("  jarvis-host-probe [command]")
        print("  jarvis-host-probe --health")
        print("  jarvis-host-probe --audit-status")
        print("  jarvis-host-probe --readiness")
        print("  jarvis-host-probe --preflight")
        print("  jarvis-host-probe --plan 'shell: pwd'")
        print("  jarvis-host-probe --mode")
        print("  jarvis-host-probe --pause [reason]")
        print("  jarvis-host-probe --resume")
    }

    private static func printHealth(client: JarvisClient) async throws {
        let health = try await client.health()
        print("Jarvis worker health")
        print("OK: \(health.ok)")
        print("Project: \(health.status.projectRoot)")
        print("Python: \(health.status.python)")
        print("Platform: \(health.status.platform)")
        print("Codex: \(health.status.codex.version ?? "not detected")")
        if let runtime = health.status.runtime {
            print("PID: \(runtime.pid)")
            print("Uptime: \(formatUptime(runtime.uptimeSeconds))")
            print("Source: \(runtime.source)")
        } else {
            print("Runtime: not reported")
        }
    }

    private static func printAuditStatus(client: JarvisClient) async throws {
        let audit = try await client.auditStatus()
        print("Jarvis audit status")
        print("Events: \(audit.eventCount)")
        print("Size: \(audit.byteSizeHuman)")
        print("Retention: \(audit.retentionDays)d")
        print("Cap: \(audit.maxBytesHuman)")
        print("Path: \(audit.path)")
    }

    private static func printReadiness(client: JarvisClient) async throws {
        let readiness = try await client.readiness()
        print("Jarvis readiness summary")
        print("OK: \(readiness.ok)")
        print("Mode: \(readiness.mode.paused ? "Paused" : "Live")")
        print("Self-check: \(readiness.selfCheck.passed)/\(readiness.selfCheck.total)")
        print("Tools: \(readiness.tools.available)/\(readiness.tools.total)")
        print("Audit events: \(readiness.audit.eventCount)")
        print("Codex: \(readiness.worker.codexVersion ?? "not detected")")
        if let verification = readiness.verification, verification.available {
            let state = verification.ok == true ? "passed" : "failed"
            let passed = verification.passed ?? 0
            let total = verification.total ?? 0
            let age = verification.ageHuman.map { ", \($0) old" } ?? ""
            let path = verification.path ?? "unknown report"
            print("Verification: \(state) \(passed)/\(total) at \(path)\(age)")
        } else {
            print("Verification: none")
        }
        if let runtime = readiness.worker.runtime {
            print("PID: \(runtime.pid)")
            print("Uptime: \(formatUptime(runtime.uptimeSeconds))")
        }
        if readiness.notes.isEmpty {
            print("Notes: none")
        } else {
            print("Notes:")
            for note in readiness.notes {
                print("- \(note)")
            }
        }
    }

    private static func printMode(client: JarvisClient) async throws {
        printMode(try await client.mode())
    }

    private static func printPreflight(client: JarvisClient) async throws {
        let preflight = try await client.preflight()
        print("Jarvis preflight summary")
        print("OK: \(preflight.ok)")
        print("Mode: \(preflight.mode.paused ? "Paused" : "Live")")
        print("Required: \(preflight.summary.requiredPassed)/\(preflight.summary.requiredTotal)")
        print("Recommended: \(preflight.summary.recommendedPassed)/\(preflight.summary.recommendedTotal)")
        print("Checks:")
        for check in preflight.checks {
            let marker = check.passed ? "pass" : "fail"
            print("- [\(marker)] \(check.label) (\(check.severity)): \(check.detail)")
        }
        if preflight.notes.isEmpty {
            print("Notes: none")
        } else {
            print("Notes:")
            for note in preflight.notes {
                print("- \(note)")
            }
        }
    }

    private static func printPlan(client: JarvisClient, command: String) async throws {
        let response = try await client.plan(command: command)
        print("Jarvis command preview")
        print("Command: \(response.command ?? command)")
        print("Tool: \(response.tool ?? "unknown")")
        print("Executed: \(response.executed.map(String.init) ?? "unknown")")
        print("Summary: \(response.summary ?? "No summary")")
        if let confirmation = response.confirmation, confirmation.required {
            print("Confirmation: \(confirmation.title) [\(confirmation.kind)]")
            if let phrase = confirmation.exactPhrase {
                print("Exact phrase: \(phrase)")
            }
        }
    }

    private static func printMode(_ mode: ModeResponse) {
        print("Jarvis command mode")
        print("Paused: \(mode.paused)")
        print("Commands enabled: \(mode.commandsEnabled)")
        print("Reason: \(mode.reason)")
        if let auditEventId = mode.auditEventId {
            print("Audit event: \(auditEventId)")
        }
    }

    private static func formatUptime(_ seconds: Double) -> String {
        let totalSeconds = max(0, Int(seconds.rounded()))
        let minutes = totalSeconds / 60
        let remainingSeconds = totalSeconds % 60
        if minutes > 0 {
            return "\(minutes)m \(remainingSeconds)s"
        }
        return "\(remainingSeconds)s"
    }
}
