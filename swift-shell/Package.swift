// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "JarvisShell",
    platforms: [
        .macOS(.v14)
    ],
    products: [
        .library(name: "JarvisClient", targets: ["JarvisClient"]),
        .library(name: "JarvisMacNative", targets: ["JarvisMacNative"]),
        .executable(name: "jarvis-browser-page-probe", targets: ["JarvisBrowserPageProbe"]),
        .executable(name: "jarvis-browser-permission-probe", targets: ["JarvisBrowserPermissionProbe"]),
        .executable(name: "jarvis-host-probe", targets: ["JarvisHostProbe"]),
        .executable(name: "jarvis-menu-bar", targets: ["JarvisMenuBar"]),
        .executable(name: "jarvis-status-helper", targets: ["JarvisStatusHelper"]),
        .executable(name: "jarvis-visible-screen-probe", targets: ["JarvisVisibleScreenProbe"])
    ],
    targets: [
        .target(name: "JarvisClient"),
        .target(
            name: "JarvisMacNative",
            dependencies: ["JarvisClient"]
        ),
        .executableTarget(
            name: "JarvisBrowserPageProbe",
            dependencies: ["JarvisMacNative"]
        ),
        .executableTarget(
            name: "JarvisBrowserPermissionProbe",
            dependencies: ["JarvisMacNative"]
        ),
        .executableTarget(
            name: "JarvisHostProbe",
            dependencies: ["JarvisClient"]
        ),
        .executableTarget(
            name: "JarvisMenuBar",
            dependencies: ["JarvisClient", "JarvisMacNative"]
        ),
        .executableTarget(
            name: "JarvisStatusHelper",
            dependencies: ["JarvisClient", "JarvisMacNative"]
        ),
        .executableTarget(
            name: "JarvisVisibleScreenProbe",
            dependencies: ["JarvisClient", "JarvisMacNative"]
        ),
    ]
)
