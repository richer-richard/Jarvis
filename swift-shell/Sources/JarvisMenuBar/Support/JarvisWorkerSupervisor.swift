import Foundation
import JarvisClient

@MainActor
final class JarvisWorkerSupervisor {
    private let client: JarvisClient
    private var process: Process?
    private var monitorTask: Task<Void, Never>?
    private var startupTask: Task<WorkerStartupStatus, Never>?

    init(client: JarvisClient) {
        self.client = client
    }

    func ensureRunning() async -> WorkerStartupStatus {
        if let startupTask {
            return await startupTask.value
        }

        let task = Task { @MainActor [weak self] in
            guard let self else {
                return WorkerStartupStatus.failed("Worker supervisor was released during startup.")
            }
            return await self.performEnsureRunning()
        }
        startupTask = task
        let status = await task.value
        startupTask = nil
        return status
    }

    private func performEnsureRunning() async -> WorkerStartupStatus {
        supervisorLog("ensureRunning started")
        if await isHealthy() {
            supervisorLog("worker already healthy")
            return .alreadyRunning
        }

        let environment = ProcessInfo.processInfo.environment
        if ["1", "true", "yes"].contains(environment["JARVIS_DISABLE_WORKER_AUTOSTART"]?.lowercased() ?? "") {
            supervisorLog("autostart disabled by environment")
            return .disabled
        }
        guard isLocalhost(client.baseURL) else {
            supervisorLog("unsupported worker url \(client.baseURL.absoluteString)")
            return .unsupportedURL(client.baseURL.absoluteString)
        }
        guard let projectRoot = findProjectRoot(environment: environment) else {
            supervisorLog("worker script not found")
            return .missingProjectRoot
        }

        do {
            supervisorLog("starting worker at \(projectRoot.path)", projectRoot: projectRoot)
            let process = Process()
            process.executableURL = URL(fileURLWithPath: "/usr/bin/env")
            process.arguments = workerArguments(projectRoot: projectRoot)
            process.currentDirectoryURL = projectRoot
            process.environment = workerEnvironment(base: environment, projectRoot: projectRoot)
            let logHandle = workerLogHandle(projectRoot: projectRoot)
            process.standardOutput = logHandle
            process.standardError = logHandle
            try process.run()
            self.process = process
            supervisorLog("worker process launched pid \(process.processIdentifier)", projectRoot: projectRoot)
        } catch {
            supervisorLog("worker launch failed \(error)", projectRoot: projectRoot)
            return .failed("Could not start Python worker: \(error)")
        }

        for _ in 0..<30 {
            try? await Task.sleep(nanoseconds: 150_000_000)
            if await isHealthy() {
                supervisorLog("worker became healthy", projectRoot: projectRoot)
                return .started
            }
            if let process, !process.isRunning {
                supervisorLog("worker exited during startup", projectRoot: projectRoot)
                return .failed("Python worker exited during startup.")
            }
        }

        supervisorLog("worker startup timed out", projectRoot: projectRoot)
        return .failed("Python worker did not become healthy before timeout.")
    }

    func stopStartedWorker() {
        guard let process else {
            return
        }
        if process.isRunning {
            process.terminate()
        }
        self.process = nil
    }

    func startMonitoring(
        intervalNanoseconds: UInt64 = 30_000_000_000,
        onStatus: @escaping @MainActor (WorkerStartupStatus) -> Void
    ) {
        guard monitorTask == nil else {
            return
        }
        monitorTask = Task { @MainActor [weak self] in
            while !Task.isCancelled {
                guard let self else {
                    return
                }
                let status = await self.ensureRunning()
                onStatus(status)
                try? await Task.sleep(nanoseconds: intervalNanoseconds)
            }
        }
    }

    func stopMonitoring() {
        monitorTask?.cancel()
        monitorTask = nil
    }

    private func isHealthy() async -> Bool {
        do {
            return try await client.health().ok
        } catch {
            return false
        }
    }

    private func workerEnvironment(base: [String: String], projectRoot: URL) -> [String: String] {
        var environment = base
        environment["PYTHONUNBUFFERED"] = "1"
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        if environment["JARVIS_APP_VOICE_DEFAULTS"] == nil {
            environment["JARVIS_APP_VOICE_DEFAULTS"] = "1"
        }
        if environment["JARVIS_TTS_AUTOMATIC_ENABLED"] == nil {
            environment["JARVIS_TTS_AUTOMATIC_ENABLED"] = "1"
        }
        if environment["JARVIS_TTS_SPEAK_STATUS"] == nil {
            environment["JARVIS_TTS_SPEAK_STATUS"] = "1"
        }
        if environment["JARVIS_TTS_PROVIDER"] == nil {
            environment["JARVIS_TTS_PROVIDER"] = "piper"
        }
        if let workspaceRoot = sourceWorkspaceRoot(),
           workspaceRoot.standardizedFileURL.path != projectRoot.standardizedFileURL.path {
            environment["JARVIS_WORKSPACE_ROOT"] = workspaceRoot.path
        }
        if let port = client.baseURL.port {
            environment["JARVIS_PORT"] = String(port)
        }
        if let host = client.baseURL.host, !host.isEmpty {
            environment["JARVIS_HOST"] = host
        }
        return environment
    }

    private func workerArguments(projectRoot: URL) -> [String] {
        var arguments = [
            "python3",
            projectRoot
                .appendingPathComponent("scripts")
                .appendingPathComponent("run_dashboard.py")
                .path,
        ]
        if let host = client.baseURL.host, !host.isEmpty {
            arguments.append(contentsOf: ["--host", host])
        }
        if let port = client.baseURL.port {
            arguments.append(contentsOf: ["--port", String(port)])
        }
        return arguments
    }

    private func findProjectRoot(environment: [String: String]) -> URL? {
        var candidates: [URL] = []
        if let bundledWorker = bundledWorkerRoot() {
            candidates.append(bundledWorker)
        }
        if let configured = environment["JARVIS_PROJECT_ROOT"], !configured.isEmpty {
            candidates.append(URL(fileURLWithPath: configured))
        }

        let current = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
        candidates.append(current)
        candidates.append(current.deletingLastPathComponent())

        if let executable = Bundle.main.executableURL {
            var cursor = executable.deletingLastPathComponent()
            for _ in 0..<10 {
                candidates.append(cursor)
                cursor.deleteLastPathComponent()
            }
        }

        var seen: Set<String> = []
        for candidate in candidates {
            let normalized = candidate.standardizedFileURL
            guard seen.insert(normalized.path).inserted else {
                continue
            }
            if hasWorkerScript(at: normalized) {
                return normalized
            }
        }

        return nil
    }

    private func bundledWorkerRoot() -> URL? {
        guard let resources = Bundle.main.resourceURL else {
            return nil
        }
        return resources.appendingPathComponent("JarvisWorker")
    }

    private func sourceWorkspaceRoot() -> URL? {
        guard let bundleURL = Bundle.main.bundleURL as URL? else {
            return nil
        }
        var candidates: [URL] = []
        if let resourceRoot = bundledWorkspaceRootResource() {
            candidates.append(resourceRoot)
        }
        candidates.append(bundleURL.deletingLastPathComponent().deletingLastPathComponent())
        if let configured = ProcessInfo.processInfo.environment["JARVIS_PROJECT_ROOT"], !configured.isEmpty {
            candidates.append(URL(fileURLWithPath: configured))
        }
        candidates.append(URL(fileURLWithPath: FileManager.default.currentDirectoryPath))

        var seen: Set<String> = []
        for candidate in candidates {
            let normalized = candidate.standardizedFileURL
            guard seen.insert(normalized.path).inserted else {
                continue
            }
            if hasWorkerScript(at: normalized),
               FileManager.default.fileExists(atPath: normalized.appendingPathComponent("jarvis").path) {
                return normalized
            }
        }
        return nil
    }

    private func bundledWorkspaceRootResource() -> URL? {
        guard let resources = Bundle.main.resourceURL else {
            return nil
        }
        let marker = resources.appendingPathComponent("JarvisWorkspaceRoot.txt")
        guard let text = try? String(contentsOf: marker, encoding: .utf8) else {
            return nil
        }
        let path = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !path.isEmpty else {
            return nil
        }
        return URL(fileURLWithPath: path)
    }

    private func hasWorkerScript(at root: URL) -> Bool {
        let script = root
            .appendingPathComponent("scripts")
            .appendingPathComponent("run_dashboard.py")
        var isDirectory: ObjCBool = false
        return FileManager.default.fileExists(atPath: script.path, isDirectory: &isDirectory) && !isDirectory.boolValue
    }

    private func isLocalhost(_ url: URL) -> Bool {
        guard let host = url.host?.lowercased() else {
            return false
        }
        return host == "127.0.0.1" || host == "localhost" || host == "::1"
    }

    private func workerLogHandle(projectRoot: URL) -> FileHandle {
        logHandle(named: "worker-supervisor.log")
    }

    private func supervisorLog(_ message: String, projectRoot: URL? = nil) {
        let line = "\(Date()) \(message)\n"
        guard let data = line.data(using: .utf8) else {
            return
        }
        let handle = logHandle(named: "worker-supervisor-events.log")
        guard handle !== FileHandle.nullDevice else {
            return
        }
        defer {
            try? handle.close()
        }
        try? handle.write(contentsOf: data)
    }

    private func logHandle(named name: String) -> FileHandle {
        let logs = supervisorLogDirectory()
        try? FileManager.default.createDirectory(at: logs, withIntermediateDirectories: true)
        let logURL = logs.appendingPathComponent(name)
        if !FileManager.default.fileExists(atPath: logURL.path) {
            FileManager.default.createFile(atPath: logURL.path, contents: nil)
        }
        guard let handle = try? FileHandle(forWritingTo: logURL) else {
            return FileHandle.nullDevice
        }
        _ = try? handle.seekToEnd()
        return handle
    }

    private func supervisorLogDirectory() -> URL {
        let base = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
            ?? URL(fileURLWithPath: NSTemporaryDirectory())
        return base
            .appendingPathComponent("Jarvis", isDirectory: true)
            .appendingPathComponent("Logs", isDirectory: true)
    }
}

enum WorkerStartupStatus: Equatable, CustomStringConvertible {
    case alreadyRunning
    case started
    case disabled
    case unsupportedURL(String)
    case missingProjectRoot
    case failed(String)

    var isReady: Bool {
        switch self {
        case .alreadyRunning, .started:
            return true
        case .disabled, .unsupportedURL, .missingProjectRoot, .failed:
            return false
        }
    }

    var description: String {
        switch self {
        case .alreadyRunning:
            return "Worker already online"
        case .started:
            return "Worker started"
        case .disabled:
            return "Worker autostart disabled"
        case .unsupportedURL(let url):
            return "Worker autostart skipped for \(url)"
        case .missingProjectRoot:
            return "Worker script not found"
        case .failed(let message):
            return message
        }
    }
}
