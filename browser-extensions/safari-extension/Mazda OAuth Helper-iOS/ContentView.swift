//
//  ContentView.swift
//  com.mazda.oauth-helper-ios
//
//  Created by crash0verride11 on 3/10/26.
//

import SwiftUI
import SafariServices

let extensionBundleIdentifier = "com.mazda.oauth-helper.extension-ios"

struct ContentView: View {
    @EnvironmentObject private var appState: AppState

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 28) {

                    // Header icon + title
                    VStack(spacing: 12) {
                        Image(systemName: "car.fill")
                            .font(.system(size: 56))
                            .foregroundStyle(.tint)
                        Text("Mazda OAuth Helper")
                            .font(.title2.bold())
                        Text("Captures Mazda OAuth authorization codes from Safari")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                            .multilineTextAlignment(.center)
                    }
                    .padding(.top, 16)

                    // Extension setup card
                    GroupBox {
                        HStack(spacing: 12) {
                            Image(systemName: "puzzlepiece.extension")
                                .foregroundStyle(.blue)
                                .font(.title3)
                            VStack(alignment: .leading, spacing: 2) {
                                Text("Safari Extension")
                                    .font(.subheadline.bold())
                                Text("Enable in Settings to capture codes")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                            Spacer()
                            Button("Settings") {
                                openExtensionSettings()
                            }
                            .buttonStyle(.bordered)
                            .controlSize(.small)
                        }
                    } label: {
                        Label("Extension Setup", systemImage: "puzzlepiece.extension")
                    }

                    // Setup instructions
                    GroupBox {
                        VStack(alignment: .leading, spacing: 14) {
                            instructionRow(
                                number: "1",
                                title: "Enable the Extension",
                                detail: "Open Settings → Safari → Extensions, then turn on Mazda OAuth Helper."
                            )
                            Divider()
                            instructionRow(
                                number: "2",
                                title: "Start a Mazda Login",
                                detail: "Complete the Mazda login flow in Safari. The extension intercepts the redirect automatically."
                            )
                            Divider()
                            instructionRow(
                                number: "3",
                                title: "Link to HomeAssistant",
                                detail: "The app opens a webview with the 'Link to HomeAssistant' interface."
                            )
                        }
                    } label: {
                        Label("How It Works", systemImage: "info.circle")
                    }

                    // Open Settings CTA
                    Button(action: openExtensionSettings) {
                        Label("Open Safari Settings", systemImage: "arrow.up.right.square")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.large)

                }
                .padding()
            }
            .navigationTitle("Mazda OAuth Helper")
            .navigationBarTitleDisplayMode(.inline)
            .sheet(isPresented: $appState.showCapture) {
                CaptureView()
                    .environmentObject(appState)
            }
        }
    }

    // MARK: - Sub-views

    private func instructionRow(number: String, title: String, detail: String) -> some View {
        HStack(alignment: .top, spacing: 12) {
            Text(number)
                .font(.caption.bold())
                .foregroundStyle(.white)
                .frame(width: 24, height: 24)
                .background(Color.accentColor)
                .clipShape(Circle())
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.subheadline.bold())
                Text(detail)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    // MARK: - Actions

    private func openExtensionSettings() {
        if let url = URL(string: UIApplication.openSettingsURLString) {
            UIApplication.shared.open(url)
        }
    }
}

#Preview {
    ContentView()
        .environmentObject(AppState())
}
