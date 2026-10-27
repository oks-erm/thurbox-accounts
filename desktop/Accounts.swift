import AppKit
import Foundation
import SwiftUI

struct BackendConfig: Codable { let argv: [String] }
struct Account: Codable, Identifiable {
    let name: String
    let label: String
    let email: String
    var id: String { name }
}
struct Conversation: Codable, Identifiable {
    let id: String
    let name: String
    let cwd: String
    let profile: String
    let next_profile: String?
    let conversation: String?
    let shared: Bool
    let stopped: Bool
    let phase: String
}
struct Snapshot: Codable { let profiles: [Account]; let conversations: [Conversation] }
struct BackendError: LocalizedError { let message: String; var uncertain = false; var errorDescription: String? { message } }

final class Buffer: @unchecked Sendable {
    private let lock = NSLock()
    private var bytes = Data()
    private var exceeded = false
    func append(_ data: Data) {
        lock.lock(); defer { lock.unlock() }
        let remaining = max(0, 2_000_000 - bytes.count)
        bytes.append(data.prefix(remaining))
        if data.count > remaining { exceeded = true }
    }
    func result() -> (Data, Bool) { lock.lock(); defer { lock.unlock() }; return (bytes, exceeded) }
}

struct Bridge {
    let argv: [String]
    static func load() throws -> Bridge {
        let url = ProcessInfo.processInfo.environment["THURBOX_ACCOUNTS_DESKTOP_CONFIG"].map { URL(fileURLWithPath: $0) }
            ?? Bundle.main.url(forResource: "backend", withExtension: "json")
        guard let url else { throw BackendError(message: "Backend configuration is missing. Run desktop-install again.") }
        let config = try JSONDecoder().decode(BackendConfig.self, from: Data(contentsOf: url))
        guard config.argv.count >= 2, config.argv[0].hasPrefix("/") else { throw BackendError(message: "Backend command must use an absolute interpreter path.") }
        return Bridge(argv: config.argv)
    }
    func call(_ args: [String], timeout: Double = 180) async throws -> Data {
        try await withCheckedThrowingContinuation { continuation in
            DispatchQueue.global(qos: .userInitiated).async {
                do { continuation.resume(returning: try self.execute(args, timeout: timeout)) }
                catch { continuation.resume(throwing: error) }
            }
        }
    }
    func execute(_ args: [String], timeout: Double) throws -> Data {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: argv[0])
        process.arguments = Array(argv.dropFirst()) + ["--desktop-deadline", String(timeout)] + args
        process.currentDirectoryURL = FileManager.default.homeDirectoryForCurrentUser
        var env = ProcessInfo.processInfo.environment
        env["PATH"] = ["/opt/homebrew/bin", "/usr/local/bin", FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent(".local/bin").path, env["PATH"] ?? "/usr/bin:/bin"].joined(separator: ":")
        process.environment = env
        let out = Pipe(), err = Pipe(), output = Buffer(), errors = Buffer()
        process.standardOutput = out; process.standardError = err; process.standardInput = FileHandle.nullDevice
        let done = DispatchSemaphore(value: 0)
        process.terminationHandler = { _ in done.signal() }
        try process.run()
        let readers = DispatchGroup()
        for (pipe, buffer) in [(out, output), (err, errors)] {
            readers.enter()
            DispatchQueue.global().async {
                defer { readers.leave() }
                while let data = try? pipe.fileHandleForReading.read(upToCount: 65536), !data.isEmpty { buffer.append(data) }
            }
        }
        let timedOut = done.wait(timeout: .now() + timeout + 15) == .timedOut
        if timedOut {
            process.terminate()
            if done.wait(timeout: .now() + 10) == .timedOut { kill(process.processIdentifier, SIGKILL); process.waitUntilExit() }
        }
        _ = readers.wait(timeout: .now() + 2)
        let (data, truncated) = output.result(), (diagnostic, errorsTruncated) = errors.result()
        if timedOut { throw BackendError(message: "Backend shutdown could not be confirmed. Inspect existing sessions before reopening this app; further actions are disabled.", uncertain: true) }
        if truncated || errorsTruncated { throw BackendError(message: "Backend output exceeded its supported size.") }
        if process.terminationStatus != 0 {
            throw BackendError(message: String(data: diagnostic, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines).nilIfEmpty ?? "Backend command failed. Check the selected account and conversation.")
        }
        return data
    }
}
extension String { var nilIfEmpty: String? { isEmpty ? nil : self } }

@MainActor final class Model: ObservableObject {
    @Published var accounts: [Account] = []
    @Published var conversations: [Conversation] = []
    @Published var selected: String? {
        didSet {
            guard oldValue != selected else { return }
            if let oldValue { drafts[oldValue] = prompt }
            prompt = selected.flatMap { drafts[$0] } ?? ""
            output = "Loading conversation…"
            revision += 1
        }
    }
    private var drafts: [String: String] = [:]
    @Published var profile = ""
    @Published var order = ""
    @Published var newProfile = ""
    @Published var prompt = ""
    @Published var output = "Select a conversation, or add your first account."
    @Published var notice = ""
    @Published var error = ""
    @Published var busy = false
    @Published var refreshing = false
    @Published var blocked = false
    let bridge: Bridge?
    private var revision = 0
    var current: Conversation? { conversations.first { $0.id == selected } }
    var orderedProfiles: [String] { order.split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty } }
    init() {
        do { bridge = try Bridge.load() }
        catch { bridge = nil; self.error = error.localizedDescription }
    }
    func refresh() async {
        guard !busy, !refreshing, let bridge else { return }
        refreshing = true; let generation = revision; defer { refreshing = false }
        do {
            let snapshot = try JSONDecoder().decode(Snapshot.self, from: await bridge.call(["desktop-state"]))
            guard generation == revision else { return }
            accounts = snapshot.profiles; conversations = snapshot.conversations
            if !accounts.contains(where: { $0.name == profile }) { profile = accounts.first?.name ?? "" }
            if selected == nil { selected = conversations.first?.id }
            if let id = selected, !conversations.contains(where: { $0.id == id }) { selected = conversations.first?.id }
            if let id = selected {
                let data = try await bridge.call(["desktop-capture", id])
                if generation == revision, selected == id, let value = try JSONSerialization.jsonObject(with: data) as? [String: Any] { output = value["output"] as? String ?? "" }
            } else { output = "Add an account and finish its native SSO login, then create a conversation." }
        } catch { self.error = error.localizedDescription }
    }
    func perform(_ args: [String], message: String = "Done.", timeout: Double = 180, clearPrompt: Bool = false) {
        guard !busy, !blocked, let bridge else { return }
        revision += 1
        busy = true; error = ""; notice = "Working…"
        Task {
            do {
                let data = try await bridge.call(args, timeout: timeout)
                let value = try JSONSerialization.jsonObject(with: data) as? [String: Any]
                if let value, let id = (value["session"] ?? value["id"]) as? String,
                   args.first == "switch" || args.first == "start" || args.first == "enable-shared" || args.first == "recover-shared" { selected = id }
                if args.first == "add", let name = value?["name"] as? String { profile = name; newProfile = "" }
                if clearPrompt { prompt = "" }
                if args.first == "status" {
                    notice = value?["loggedIn"] as? Bool == true ? "Signed in as \(value?["email"] as? String ?? profile)." : "This profile is signed out. Click Log in to finish SSO."
                } else { notice = value?["notice"] as? String ?? message }
            } catch { self.error = error.localizedDescription; notice = ""; if (error as? BackendError)?.uncertain == true { blocked = true } }
            busy = false
            await refresh()
        }
    }
    func login() {
        guard !busy, let bridge, !profile.isEmpty else { return }
        do {
            let dir = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0].appendingPathComponent("ThurboxAccounts")
            try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
            let script = dir.appendingPathComponent("login-\(UUID().uuidString).command")
            let quote: (String) -> String = { "'" + $0.replacingOccurrences(of: "'", with: "'\\''") + "'" }
            try ("#!/bin/sh\nexport PATH=/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:/usr/bin:/bin\nexec " + (bridge.argv + ["login", profile]).map(quote).joined(separator: " ") + "\n").write(to: script, atomically: true, encoding: .utf8)
            try FileManager.default.setAttributes([.posixPermissions: 0o700], ofItemAtPath: script.path)
            guard NSWorkspace.shared.open(script) else { throw BackendError(message: "Could not open native SSO in Terminal.") }
            notice = "Finish SSO in Terminal and your browser, then click Check login."
        } catch { self.error = error.localizedDescription }
    }
    func create() {
        guard !busy, !profile.isEmpty else { return }
        let panel = NSOpenPanel(); panel.canChooseDirectories = true; panel.canChooseFiles = false; panel.allowsMultipleSelection = false
        panel.message = "Choose the project for this account's conversation."
        if panel.runModal() == .OK, let folder = panel.url { perform(["start", profile, "--repo", folder.path, "--name", folder.lastPathComponent], message: "Conversation created. Read its native prompt below.") }
    }
}

struct CompanionView: View {
    @StateObject private var model = Model()
    @State private var confirm: Confirmation?
    enum Confirmation: String, Identifiable { case verify, enable, stop; var id: String { rawValue } }
    var body: some View {
        HSplitView {
            VStack(alignment: .leading, spacing: 16) {
                Label("Accounts", systemImage: "person.crop.circle.badge.checkmark").font(.title2.bold())
                Picker("Account", selection: $model.profile) {
                    Text("Choose an account").tag("")
                    ForEach(model.accounts) { Text($0.label).tag($0.name) }
                }
                if let account = model.accounts.first(where: { $0.name == model.profile }) {
                    Text(account.email).font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
                }
                HStack {
                    Button("Log in…") { model.login() }.disabled(model.profile.isEmpty)
                    Button("Check login") { model.perform(["status", model.profile], message: "Login checked.") }.disabled(model.profile.isEmpty)
                }
                HStack {
                    TextField("Account name, e.g. work-a", text: $model.newProfile)
                    Button("Add") { model.perform(["add", model.newProfile], message: "Account added. Select it and log in.") }.disabled(model.newProfile.isEmpty)
                }
                Button("New conversation…", action: model.create).disabled(model.profile.isEmpty)
                Divider()
                Text("Conversations").font(.headline)
                if model.conversations.isEmpty {
                    VStack(spacing: 10) {
                        Image(systemName: "bubble.left.and.bubble.right").font(.title).foregroundStyle(.secondary)
                        Text("No conversations yet").font(.callout)
                    }.frame(maxWidth: .infinity, maxHeight: .infinity)
                } else {
                    List(selection: $model.selected) {
                        ForEach(model.conversations) { row in
                            VStack(alignment: .leading, spacing: 3) {
                                Text(row.name).lineLimit(1)
                                Text("\(row.profile) · \(row.shared ? "shared" : "single account") · \(row.phase)").font(.caption).foregroundStyle(.secondary)
                            }.padding(.vertical, 3).tag(row.id)
                        }
                    }.listStyle(.sidebar)
                }
                DisclosureGroup("Set up shared history") {
                    VStack(alignment: .leading, spacing: 9) {
                        TextField("work-a,work-b — switching order", text: $model.order)
                        Text("Only these accounts will have access to the selected conversation.").font(.caption).foregroundStyle(.secondary)
                        Button("Verify accounts…") { confirm = .verify }.disabled(model.orderedProfiles.count < 2)
                        Button("Enable for selected conversation…") { confirm = .enable }.disabled(model.orderedProfiles.count < 2 || model.current == nil || model.current?.shared == true || model.current?.stopped != true)
                        Text("Stop an idle conversation before enabling sharing. Verification uses account allowance.").font(.caption).foregroundStyle(.secondary)
                    }.padding(.top, 8)
                }
            }.padding(18).frame(minWidth: 300, idealWidth: 330, maxWidth: 400).disabled(model.busy)
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    VStack(alignment: .leading) {
                        Text(model.current?.name ?? "Your conversations").font(.title2.bold())
                        Text(model.current.map { "Account: \($0.profile)" } ?? "Separate logins. One selected history.").foregroundStyle(.secondary)
                    }
                    Spacer()
                    if model.busy { ProgressView().controlSize(.small) }
                    Button { Task { await model.refresh() } } label: { Image(systemName: "arrow.clockwise") }.help("Refresh").disabled(model.busy)
                    if let row = model.current, row.shared, let next = row.next_profile, let conversation = row.conversation {
                        Button("Switch to \(next)") { model.perform(["switch", conversation, "--expected-profile", next], message: "Switched to \(next).") }.buttonStyle(.borderedProminent).disabled(model.busy)
                    }
                }
                if !model.error.isEmpty {
                    HStack(alignment: .top) {
                        Image(systemName: "exclamationmark.triangle.fill")
                        Text(model.error).textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading)
                        Button { model.error = "" } label: { Image(systemName: "xmark") }.buttonStyle(.plain)
                    }.padding(10).background(Color.orange.opacity(0.12)).cornerRadius(8)
                }
                if !model.notice.isEmpty { Text(model.notice).font(.callout).foregroundStyle(.secondary) }
                if model.current == nil {
                    VStack(spacing: 16) {
                        Image(systemName: "person.crop.circle.badge.plus").font(.system(size: 40)).foregroundStyle(.tint)
                        Text("Start with an account").font(.title2.bold())
                        Text("Add your Enterprise accounts, finish SSO, then choose a project with New conversation.")
                            .foregroundStyle(.secondary).multilineTextAlignment(.center).frame(maxWidth: 380)
                        Text("Once sharing is enabled, switch accounts here without rebuilding the conversation.")
                            .font(.callout).foregroundStyle(.secondary).multilineTextAlignment(.center).frame(maxWidth: 380)
                    }.frame(maxWidth: .infinity, maxHeight: .infinity)
                } else {
                    ScrollView {
                        Text(model.output).font(.system(size: 12, design: .monospaced)).textSelection(.enabled)
                            .fixedSize(horizontal: false, vertical: true).frame(maxWidth: .infinity, alignment: .leading).padding(12)
                    }.background(Color(nsColor: .textBackgroundColor)).cornerRadius(10).frame(maxWidth: .infinity, maxHeight: .infinity)
                }
                if let row = model.current {
                    HStack {
                        Text("Native prompt controls").font(.caption).foregroundStyle(.secondary)
                        ForEach([("Enter", "enter"), ("Esc", "escape"), ("↑", "up"), ("↓", "down"), ("Interrupt", "C-c")], id: \.0) { title, key in
                            Button(title) { model.perform(["desktop-key", row.id, key], message: "") }.disabled(row.stopped)
                        }
                        Spacer()
                        if row.stopped && row.phase != "failed" && row.phase != "switching" {
                            Button("Resume") { model.perform(["desktop-start", row.id], message: "Resuming conversation…") }
                        } else if !row.stopped { Button("Stop…") { confirm = .stop } }
                        if row.shared, let conversation = row.conversation, row.phase == "failed" || row.phase == "switching" {
                            Button("Recover") { model.perform(["recover-shared", conversation], message: "Recovered reserved conversation.") }
                        }
                    }.disabled(model.busy)
                    TextEditor(text: $model.prompt).font(.body).frame(height: 68).border(Color.secondary.opacity(0.25)).disabled(model.busy || row.stopped)
                    HStack {
                        Text("Send submits your text to this account. Native trust and permission prompts require your choice.").font(.caption).foregroundStyle(.secondary)
                        Spacer()
                        Button("Send") { model.perform(["desktop-send", row.id, "--", model.prompt], message: "Sent.", clearPrompt: true) }.keyboardShortcut(.return, modifiers: .command).buttonStyle(.borderedProminent).disabled(model.busy || row.stopped || model.prompt.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    }
                }
            }.padding(20).frame(minWidth: 600)
        }.frame(minWidth: 960, minHeight: 680).disabled(model.blocked)
        .task { while !Task.isCancelled { await model.refresh(); try? await Task.sleep(nanoseconds: 2_000_000_000) } }
        .onChange(of: model.selected) { _ in model.output = "Loading conversation…"; Task { await model.refresh() } }
        .alert(item: $confirm) { choice in
            switch choice {
            case .verify:
                return Alert(title: Text("Verify selected accounts?"), message: Text("Order: \(model.orderedProfiles.joined(separator: " → "))\n\nThis sends synthetic model requests using these accounts' allowance. Two profiles require six top-level calls plus a subagent; each top-level call uses --max-budget-usd 0.25. No existing conversation is sent."), primaryButton: .default(Text("Run verification")) { model.perform(["verify-shared"] + model.orderedProfiles, message: "Verification passed. You can enable shared history.", timeout: 900) }, secondaryButton: .cancel())
            case .enable:
                let id = model.current?.id ?? ""
                let args = ["enable-shared", "--session", id, "--consent"] + model.orderedProfiles.flatMap { ["--profile", $0] }
                return Alert(title: Text("Share this conversation?"), message: Text("\(model.current?.name ?? "Conversation")\n\nAccounts: \(model.orderedProfiles.joined(separator: " → "))\n\nThese accounts and their organizations can use this conversation's context. Logins remain separate. Sharing applies only to this conversation and its sidecars."), primaryButton: .default(Text("Enable sharing")) { model.perform(args, message: "Sharing enabled. Use the Switch button to continue under the next account.") }, secondaryButton: .cancel())
            case .stop:
                let id = model.current?.id ?? ""
                return Alert(title: Text("Stop this conversation?"), message: Text("Stop only at a safe point after tools and subagents finish. History is retained. The shared launcher refuses switching if worker activity is unconfirmed."), primaryButton: .default(Text("Stop conversation")) { model.perform(["desktop-stop", id], message: "Conversation stopped; history retained.") }, secondaryButton: .cancel())
            }
        }
    }
}

@MainActor @main struct AccountsCompanion: App {
    init() {
        if ProcessInfo.processInfo.arguments.contains("--ui-model-check") {
            let model = Model()
            model.selected = "account-a-conversation"
            model.prompt = "draft for account A"
            model.selected = "account-b-conversation"
            guard model.prompt.isEmpty else { fatalError("A draft crossed conversation boundaries") }
            model.prompt = "draft for account B"
            model.selected = "account-a-conversation"
            guard model.prompt == "draft for account A" else { fatalError("A draft was not restored") }
            print("{\"draft_isolation\":true}")
            exit(0)
        }
        if ProcessInfo.processInfo.arguments.contains("--bridge-check") {
            do {
                let data = try Bridge.load().execute(["desktop-state"], timeout: 20)
                _ = try JSONDecoder().decode(Snapshot.self, from: data)
                FileHandle.standardOutput.write(data)
                exit(0)
            } catch {
                FileHandle.standardError.write(Data((error.localizedDescription + "\n").utf8))
                exit(1)
            }
        }
    }
    var body: some Scene {
        WindowGroup("Thurbox Accounts") { CompanionView() }
            .commands { CommandGroup(replacing: .newItem) {} }
    }
}
