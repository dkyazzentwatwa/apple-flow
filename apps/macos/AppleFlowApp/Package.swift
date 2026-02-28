// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "AppleFlowApp",
    platforms: [.macOS(.v13)],
    products: [
        .executable(name: "AppleFlowApp", targets: ["AppleFlowApp"]),
    ],
    targets: [
        .executableTarget(
            name: "AppleFlowApp",
            path: "Sources/AppleFlowApp"
        ),
        .testTarget(
            name: "AppleFlowAppTests",
            dependencies: ["AppleFlowApp"],
            path: "Tests/AppleFlowAppTests"
        ),
    ]
)
