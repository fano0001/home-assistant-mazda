//
//  AppDelegate.swift
//  Mazda OAuth Helper
//
//  Created by crash0verride11 on 2/19/26.
//

import Cocoa
import SafariServices
import WebKit
import UserNotifications

@main
class AppDelegate: NSObject, NSApplicationDelegate {
    
    var captureWindow: NSWindow?

    func applicationDidFinishLaunching(_ notification: Notification) {
        // Register to handle URL events
        NSAppleEventManager.shared().setEventHandler(
            self,
            andSelector: #selector(handleGetURLEvent(_:withReplyEvent:)),
            forEventClass: AEEventClass(kInternetEventClass),
            andEventID: AEEventID(kAEGetURL)
        )
        
        // Request notification permissions
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound]) { granted, error in
            if let error = error {
                print("Notification authorization error: \(error)")
            }
        }
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        return true
    }
    
    @objc func handleGetURLEvent(_ event: NSAppleEventDescriptor, withReplyEvent replyEvent: NSAppleEventDescriptor) {
        guard let urlString = event.paramDescriptor(forKeyword: AEKeyword(keyDirectObject))?.stringValue,
              let url = URL(string: urlString) else {
            return
        }
        
        handleMazdaURL(url)
    }
    
    func application(_ application: NSApplication, open urls: [URL]) {
        for url in urls {
            handleMazdaURL(url)
        }
    }
    
    private func handleMazdaURL(_ url: URL) {
        print("App received URL: \(url.absoluteString)")
        
        // Extract the authorization code and other parameters
        let components = URLComponents(url: url, resolvingAgainstBaseURL: false)
        let code = components?.queryItems?.first(where: { $0.name == "code" })?.value
        let state = components?.queryItems?.first(where: { $0.name == "state" })?.value
        let error = components?.queryItems?.first(where: { $0.name == "error" })?.value
        let errorDescription = components?.queryItems?.first(where: { $0.name == "error_description" })?.value
        
        // Check if this is a Home Assistant flow (state is a JWT with flow_id)
        let isHomeAssistantFlow = checkIfHomeAssistantFlow(state: state)
        
        if let code = code, isHomeAssistantFlow {
            // Redirect to Home Assistant OAuth endpoint
            var haComponents = URLComponents(string: "https://my.home-assistant.io/redirect/oauth")
            haComponents?.queryItems = [
                URLQueryItem(name: "code", value: code),
                URLQueryItem(name: "state", value: state ?? "")
            ]
            
            if let haURL = haComponents?.url {
                print("Redirecting to Home Assistant: \(haURL.absoluteString)")
                NSWorkspace.shared.open(haURL)
                showNotification(title: "Redirecting to Home Assistant", message: "Opening Home Assistant with authorization code")
                return
            }
        }
        
        // Otherwise, show the capture page in a window
        showCaptureWindow(code: code, state: state, error: error, errorDescription: errorDescription)
    }
    
    private func checkIfHomeAssistantFlow(state: String?) -> Bool {
        guard let state = state else { return false }
        
        print("Checking if Home Assistant flow for state: \(state)")
        
        // Check if state is a JWT with flow_id (for Home Assistant)
        let parts = state.split(separator: ".")
        guard parts.count == 3 else {
            print("State is not a JWT (doesn't have 3 parts)")
            return false
        }
        
        // Decode the payload (middle part)
        // JWT uses base64url encoding, so we need to convert it to standard base64
        var base64 = String(parts[1])
            .replacingOccurrences(of: "-", with: "+")
            .replacingOccurrences(of: "_", with: "/")
        
        // Add padding if needed
        let remainder = base64.count % 4
        if remainder > 0 {
            base64 += String(repeating: "=", count: 4 - remainder)
        }
        
        print("Attempting to decode JWT payload: \(base64)")
        
        guard let payloadData = Data(base64Encoded: base64),
              let payload = try? JSONSerialization.jsonObject(with: payloadData) as? [String: Any] else {
            print("Failed to decode JWT payload")
            return false
        }
        
        print("Decoded JWT payload: \(payload)")
        
        if let flowId = payload["flow_id"] as? String, !flowId.isEmpty {
            print("Found flow_id: \(flowId) - this is a Home Assistant flow!")
            return true
        }
        
        print("No flow_id found in JWT payload")
        return false
    }
    
    private func showNotification(title: String, message: String) {
        let content = UNMutableNotificationContent()
        content.title = title
        content.body = message
        content.sound = .default
        
        let request = UNNotificationRequest(
            identifier: UUID().uuidString,
            content: content,
            trigger: nil
        )
        
        UNUserNotificationCenter.current().add(request) { error in
            if let error = error {
                print("Notification error: \(error)")
            }
        }
    }
    
    private func showCaptureWindow(code: String?, state: String?, error: String?, errorDescription: String?) {
        // Close existing window if present
        captureWindow?.close()
        
        // Create a new window
        let window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 600, height: 400),
            styleMask: [.titled, .closable, .miniaturizable],
            backing: .buffered,
            defer: false
        )
        
        window.title = "Mazda OAuth - Code Captured"
        window.center()
        window.isReleasedWhenClosed = false
        
        // Create a WebView to display the capture page
        let webView = WKWebView(frame: window.contentView!.bounds)
        webView.autoresizingMask = [.width, .height]
        
        // Load the HTML content
        let htmlContent = generateCaptureHTML(code: code, state: state, error: error, errorDescription: errorDescription)
        webView.loadHTMLString(htmlContent, baseURL: nil)
        
        window.contentView = webView
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        
        self.captureWindow = window
        
        if code != nil {
            showNotification(title: "Mazda OAuth Code Captured", message: "Authorization code captured successfully!")
        } else if error != nil {
            showNotification(title: "OAuth Error", message: errorDescription ?? "An error occurred")
        }
    }
    
    private func generateCaptureHTML(code: String?, state: String?, error: String?, errorDescription: String?) -> String {
        let hasCode = code != nil && !code!.isEmpty
        let maskedCode = hasCode ? maskCode(code!) : ""
        let actualCode = code ?? ""
        
        return """
        <!doctype html>
        <html lang="en">
          <head>
            <meta charset="UTF-8" />
            <meta name="viewport" content="width=device-width, initial-scale=1.0" />
            <title>Mazda OAuth - Code Captured</title>
            <style>
              * {
                box-sizing: border-box;
                margin: 0;
                padding: 0;
              }

              body {
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                background: linear-gradient(135deg, #1a5276 0%, #2e86ab 100%);
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 20px;
              }

              .container {
                background: white;
                border-radius: 12px;
                box-shadow: 0 10px 40px rgba(0, 0, 0, 0.2);
                max-width: 600px;
                width: 100%;
                padding: 40px;
                text-align: center;
              }

              h1 {
                color: #1a5276;
                font-size: 24px;
                margin-bottom: 10px;
              }

              p {
                color: #666;
                font-size: 14px;
                margin-bottom: 20px;
              }

              .icon {
                width: 80px;
                height: 80px;
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                margin: 0 auto 20px;
              }

              .icon-success {
                background: #4caf50;
              }
              .icon-error {
                background: #f44336;
              }

              .icon svg {
                width: 40px;
                height: 40px;
                fill: white;
              }

              .code-box {
                display: flex;
                align-items: stretch;
                background: #f5f5f5;
                border: 1px solid #ddd;
                border-radius: 8px;
                overflow: hidden;
                margin: 20px 0;
              }

              .code-display {
                flex: 1;
                background: #fff;
                padding: 14px 16px;
                font-family: "Consolas", "Monaco", monospace;
                font-size: 14px;
                color: #333;
                letter-spacing: 2px;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
              }

              .copy-btn {
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 0 16px;
                border: none;
                border-left: 1px solid #ddd;
                background: #f5f5f5;
                cursor: pointer;
                transition: background 0.2s;
              }

              .copy-btn:hover {
                background: #e8e8e8;
              }

              .copy-btn svg {
                width: 20px;
                height: 20px;
                fill: #555;
              }

              .copy-btn:hover svg {
                fill: #1a5276;
              }

              .toast {
                position: fixed;
                bottom: 20px;
                left: 50%;
                transform: translateX(-50%);
                background: #333;
                color: white;
                padding: 12px 24px;
                border-radius: 6px;
                font-size: 14px;
                opacity: 0;
                transition: opacity 0.3s;
              }

              .toast.show {
                opacity: 1;
              }
            </style>
          </head>
          <body>
            <div class="container">
              \(hasCode ? """
              <div id="success">
                <div class="icon icon-success">
                  <svg viewBox="0 0 24 24">
                    <path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z" />
                  </svg>
                </div>
                <h1>Mazda Authorization Code Captured!</h1>
                <p>Copy this code and paste it in your application.</p>

                <div class="code-box">
                  <div class="code-display" id="authCode">\(maskedCode)</div>
                  <button class="copy-btn" id="copyCode" title="Copy to clipboard">
                    <svg viewBox="0 0 24 24">
                      <path d="M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z" />
                    </svg>
                  </button>
                </div>
              </div>
              """ : """
              <div id="noCode">
                <div class="icon icon-error">
                  <svg viewBox="0 0 24 24">
                    <path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z" />
                  </svg>
                </div>
                <h1>\(error != nil ? "OAuth Error" : "No Authorization Code")</h1>
                <p>\(errorDescription ?? "No code was captured. Please complete the Mazda login flow first.")</p>
              </div>
              """)
            </div>

            <div class="toast" id="toast">Copied!</div>

            <script>
              const code = "\(actualCode.replacingOccurrences(of: "\"", with: "\\\""))";
              
              document.getElementById("copyCode")?.addEventListener("click", () => {
                // Create a temporary textarea to copy the code
                const textarea = document.createElement('textarea');
                textarea.value = code;
                textarea.style.position = 'fixed';
                textarea.style.opacity = '0';
                document.body.appendChild(textarea);
                textarea.select();
                document.execCommand('copy');
                document.body.removeChild(textarea);
                
                const toast = document.getElementById("toast");
                toast.classList.add("show");
                setTimeout(() => toast.classList.remove("show"), 2000);
              });
            </script>
          </body>
        </html>
        """
    }
    
    private func maskCode(_ code: String) -> String {
        let visibleChars = 4
        guard code.count > visibleChars else { return code }
        let masked = String(repeating: "•", count: code.count - visibleChars)
        let visible = code.suffix(visibleChars)
        return masked + visible
    }

}
