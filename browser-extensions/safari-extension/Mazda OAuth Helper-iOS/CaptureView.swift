//
//  CaptureView.swift
//  com.mazda.oauth-helper-ios
//
//  Created by crash0verride11 on 3/10/26.
//

import SwiftUI

struct CaptureView: View {
    @EnvironmentObject private var appState: AppState
    @Environment(\.dismiss) private var dismiss

    @State private var showFullCode = false
    @State private var copied = false

    // MARK: - Derived state

    private var hasCode: Bool { !(appState.capturedCode ?? "").isEmpty }
    private var hasError: Bool { !(appState.capturedError ?? "").isEmpty }

    private var maskedCode: String {
        guard let code = appState.capturedCode, !code.isEmpty else { return "" }
        let visibleChars = 4
        guard code.count > visibleChars else { return code }
        let dots = String(repeating: "•", count: code.count - visibleChars)
        return dots + code.suffix(visibleChars)
    }

    // MARK: - Body

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 28) {
                    if hasCode {
                        successContent
                    } else {
                        errorContent
                    }
                }
                .padding()
                .padding(.top, 8)
            }
            .navigationTitle(hasCode ? "Code Captured" : (hasError ? "OAuth Error" : "No Code"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss() }
                }
            }
        }
    }

    // MARK: - Success content

    private var successContent: some View {
        VStack(spacing: 24) {
            // Status icon
            Circle()
                .fill(Color.green)
                .frame(width: 72, height: 72)
                .overlay {
                    Image(systemName: "checkmark")
                        .font(.system(size: 32, weight: .bold))
                        .foregroundStyle(.white)
                }

            VStack(spacing: 6) {
                Text("Authorization Code Captured!")
                    .font(.title3.bold())
                    .multilineTextAlignment(.center)
                Text("Copy this code and paste it into your application.")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
            }

            // Code display box
            GroupBox {
                VStack(alignment: .leading, spacing: 12) {
                    HStack {
                        Text(showFullCode ? (appState.capturedCode ?? "") : maskedCode)
                            .font(.system(.body, design: .monospaced))
                            .foregroundStyle(.primary)
                            .lineLimit(3)
                            .frame(maxWidth: .infinity, alignment: .leading)

                        Button {
                            showFullCode.toggle()
                        } label: {
                            Image(systemName: showFullCode ? "eye.slash" : "eye")
                                .foregroundStyle(.secondary)
                        }
                        .buttonStyle(.plain)
                    }
                }
            } label: {
                Label("Authorization Code", systemImage: "key.fill")
            }

            // Copy button
            Button {
                copyCode()
            } label: {
                HStack {
                    Image(systemName: copied ? "checkmark" : "doc.on.doc")
                    Text(copied ? "Copied!" : "Copy Code")
                }
                .frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
            .tint(copied ? .green : .accentColor)
            .animation(.easeInOut(duration: 0.2), value: copied)

            // State value (secondary, collapsible)
            if let state = appState.capturedState, !state.isEmpty {
                GroupBox {
                    Text(state)
                        .font(.system(.caption, design: .monospaced))
                        .foregroundStyle(.secondary)
                        .lineLimit(3)
                        .frame(maxWidth: .infinity, alignment: .leading)
                } label: {
                    Label("State", systemImage: "info.circle")
                }
            }
        }
    }

    // MARK: - Error / no-code content

    private var errorContent: some View {
        VStack(spacing: 24) {
            Circle()
                .fill(hasError ? Color.red : Color.orange)
                .frame(width: 72, height: 72)
                .overlay {
                    Image(systemName: hasError ? "xmark" : "questionmark")
                        .font(.system(size: 32, weight: .bold))
                        .foregroundStyle(.white)
                }

            VStack(spacing: 6) {
                Text(hasError ? (appState.capturedError ?? "OAuth Error") : "No Authorization Code")
                    .font(.title3.bold())
                    .multilineTextAlignment(.center)
                Text(appState.capturedErrorDescription ?? "No code was captured. Please complete the Mazda login flow in Safari first.")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
            }

            Button("Dismiss") { dismiss() }
                .buttonStyle(.bordered)
                .controlSize(.large)
        }
    }

    // MARK: - Actions

    private func copyCode() {
        guard let code = appState.capturedCode else { return }
        UIPasteboard.general.string = code
        withAnimation { copied = true }
        DispatchQueue.main.asyncAfter(deadline: .now() + 2) {
            withAnimation { copied = false }
        }
    }
}

#Preview {
    let state = AppState()
    state.capturedCode = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.abc123"
    state.showCapture = true
    return CaptureView()
        .environmentObject(state)
}
