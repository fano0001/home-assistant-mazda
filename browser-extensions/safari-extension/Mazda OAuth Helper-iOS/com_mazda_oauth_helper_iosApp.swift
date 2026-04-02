//
//  com_mazda_oauth_helper_iosApp.swift
//  com.mazda.oauth-helper-ios
//
//  Created by crash0verride11 on 3/10/26.
//

import SwiftUI
import Combine
import UserNotifications

// Shared app state passed down to all views
class AppState: ObservableObject {
    @Published var capturedCode: String?
    @Published var capturedState: String?
    @Published var capturedError: String?
    @Published var capturedErrorDescription: String?
    @Published var showCapture = false
}

@main
struct com_mazda_oauth_helper_iosApp: App {
    @StateObject private var appState = AppState()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(appState)
                .onOpenURL { url in
                    handleMazdaURL(url)
                }
                .task {
                    await requestNotificationPermissions()
                }
        }
    }

    // MARK: - Notification Permission

    private func requestNotificationPermissions() async {
        do {
            try await UNUserNotificationCenter.current()
                .requestAuthorization(options: [.alert, .sound])
        } catch {
            print("Notification authorization error: \(error)")
        }
    }

    // MARK: - URL Handling

    private func handleMazdaURL(_ url: URL) {
        print("App received URL: \(url.absoluteString)")

        let components = URLComponents(url: url, resolvingAgainstBaseURL: false)
        let code = components?.queryItems?.first(where: { $0.name == "code" })?.value
        let state = components?.queryItems?.first(where: { $0.name == "state" })?.value
        let error = components?.queryItems?.first(where: { $0.name == "error" })?.value
        let errorDescription = components?.queryItems?.first(where: { $0.name == "error_description" })?.value

        // Check if this is a Home Assistant flow (state is a JWT with flow_id)
        if let code = code, checkIfHomeAssistantFlow(state: state) {
            var haComponents = URLComponents(string: "https://my.home-assistant.io/redirect/oauth")
            haComponents?.queryItems = [
                URLQueryItem(name: "code", value: code),
                URLQueryItem(name: "state", value: state ?? ""),
            ]
            if let haURL = haComponents?.url {
                print("Redirecting to Home Assistant: \(haURL.absoluteString)")
                UIApplication.shared.open(haURL)
                showNotification(
                    title: "Redirecting to Home Assistant",
                    message: "Opening Home Assistant with authorization code"
                )
            }
            return
        }

        // Otherwise show the in-app capture screen
        DispatchQueue.main.async {
            self.appState.capturedCode = code
            self.appState.capturedState = state
            self.appState.capturedError = error
            self.appState.capturedErrorDescription = errorDescription
            self.appState.showCapture = true
        }

        if code != nil {
            showNotification(
                title: "Mazda OAuth Code Captured",
                message: "Authorization code captured successfully!"
            )
        } else if error != nil {
            showNotification(
                title: "OAuth Error",
                message: errorDescription ?? "An error occurred"
            )
        }
    }

    // MARK: - JWT / HA Flow Check

    private func checkIfHomeAssistantFlow(state: String?) -> Bool {
        guard let state = state else { return false }

        let parts = state.split(separator: ".")
        guard parts.count == 3 else { return false }

        var base64 = String(parts[1])
            .replacingOccurrences(of: "-", with: "+")
            .replacingOccurrences(of: "_", with: "/")

        let remainder = base64.count % 4
        if remainder > 0 {
            base64 += String(repeating: "=", count: 4 - remainder)
        }

        guard
            let payloadData = Data(base64Encoded: base64),
            let payload = try? JSONSerialization.jsonObject(with: payloadData) as? [String: Any]
        else { return false }

        if let flowId = payload["flow_id"] as? String, !flowId.isEmpty {
            print("Found flow_id: \(flowId) — this is a Home Assistant flow")
            return true
        }
        return false
    }

    // MARK: - Notifications

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
}
