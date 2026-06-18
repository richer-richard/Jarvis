import AppKit
import SwiftUI
@preconcurrency import WebKit

struct JarvisBrowserPanelView: View {
    @ObservedObject var model: JarvisShellModel
    @StateObject private var browser = JarvisEmbeddedBrowserController()

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                Button {
                    browser.goBack()
                } label: {
                    Image(systemName: "chevron.left")
                }
                .disabled(!browser.canGoBack)
                .help("Go back")

                Button {
                    browser.goForward()
                } label: {
                    Image(systemName: "chevron.right")
                }
                .disabled(!browser.canGoForward)
                .help("Go forward")

                Button {
                    browser.reload()
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
                .help("Reload")

                TextField("URL or search", text: $model.browserAddressText)
                    .textFieldStyle(.roundedBorder)
                    .onSubmit {
                        model.loadBrowserAddress()
                    }

                Button("Go") {
                    model.loadBrowserAddress()
                }
                .keyboardShortcut(.return, modifiers: [.command, .shift])

                Button {
                    model.openBrowserTargetInChrome()
                } label: {
                    Label(model.browserAuthenticatedLane ? "Open Signed-In Chrome" : "Open Chrome", systemImage: "globe")
                }
                .help("Open this page in Google Chrome")

                Button("Hide Browser") {
                    model.hideBrowser()
                }
            }

            HStack(spacing: 8) {
                Text(browser.title.isEmpty ? model.browserTitle : browser.title)
                    .font(.caption.weight(.semibold))
                    .lineLimit(1)
                    .truncationMode(.middle)
                Spacer()
                Text(model.browserStatusText)
                    .font(.caption2.monospaced())
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .truncationMode(.middle)
                if browser.isLoading {
                    ProgressView()
                        .controlSize(.small)
                    Text("Loading")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
                if model.browserAuthenticatedLane {
                    Text("Chrome Handoff")
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(.blue)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 3)
                        .background(.blue.opacity(0.12), in: Capsule())
                }
            }
            if !model.browserHintText.isEmpty {
                Text(model.browserHintText)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
                    .fixedSize(horizontal: false, vertical: true)
            }

            JarvisWebView(targetURL: model.browserTargetURL, controller: browser)
                .frame(minHeight: 280)
                .clipShape(RoundedRectangle(cornerRadius: 8))
                .overlay(
                    RoundedRectangle(cornerRadius: 8)
                        .stroke(.white.opacity(0.18), lineWidth: 1)
                )
        }
        .padding(10)
        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 8))
        .onChange(of: browser.currentURL) { _, url in
            model.noteBrowserNavigation(title: browser.title, url: url)
        }
        .onChange(of: browser.title) { _, title in
            model.noteBrowserNavigation(title: title, url: browser.currentURL)
        }
    }
}

@MainActor
final class JarvisEmbeddedBrowserController: NSObject, ObservableObject, WKNavigationDelegate, WKUIDelegate {
    @Published private(set) var title: String = ""
    @Published private(set) var currentURL: URL?
    @Published private(set) var canGoBack: Bool = false
    @Published private(set) var canGoForward: Bool = false
    @Published private(set) var isLoading: Bool = false

    private weak var webView: WKWebView?
    private var lastRequestedURL: URL?

    func attach(_ webView: WKWebView) {
        if self.webView !== webView {
            self.webView = webView
            webView.navigationDelegate = self
            webView.uiDelegate = self
        }
        refresh(from: webView)
    }

    func loadIfNeeded(_ url: URL?) {
        guard let url, lastRequestedURL != url else {
            return
        }
        lastRequestedURL = url
        webView?.load(URLRequest(url: url))
    }

    func goBack() {
        webView?.goBack()
    }

    func goForward() {
        webView?.goForward()
    }

    func reload() {
        webView?.reload()
    }

    func webView(_ webView: WKWebView, didStartProvisionalNavigation navigation: WKNavigation!) {
        refresh(from: webView)
    }

    func webView(_ webView: WKWebView, didCommit navigation: WKNavigation!) {
        refresh(from: webView)
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        refresh(from: webView)
    }

    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        refresh(from: webView)
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        refresh(from: webView)
    }

    func webView(
        _ webView: WKWebView,
        createWebViewWith configuration: WKWebViewConfiguration,
        for navigationAction: WKNavigationAction,
        windowFeatures: WKWindowFeatures
    ) -> WKWebView? {
        if navigationAction.targetFrame == nil {
            webView.load(navigationAction.request)
        }
        return nil
    }

    private func refresh(from webView: WKWebView) {
        title = webView.title ?? ""
        currentURL = webView.url
        canGoBack = webView.canGoBack
        canGoForward = webView.canGoForward
        isLoading = webView.isLoading
    }
}

private struct JarvisWebView: NSViewRepresentable {
    let targetURL: URL?
    let controller: JarvisEmbeddedBrowserController

    func makeNSView(context: Context) -> WKWebView {
        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .default()
        configuration.allowsAirPlayForMediaPlayback = true
        configuration.preferences.javaScriptCanOpenWindowsAutomatically = true
        configuration.defaultWebpagePreferences.allowsContentJavaScript = true
        let view = WKWebView(frame: .zero, configuration: configuration)
        view.customUserAgent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        view.allowsBackForwardNavigationGestures = true
        view.setValue(false, forKey: "drawsBackground")
        controller.attach(view)
        controller.loadIfNeeded(targetURL)
        return view
    }

    func updateNSView(_ view: WKWebView, context: Context) {
        controller.attach(view)
        controller.loadIfNeeded(targetURL)
    }
}
