import SwiftUI

/// The AI agent as primary interaction surface (per the plan's "AI agent
/// first" requirement) -- ask a grounded question about your own spending,
/// income, or goal progress. Backed by POST /chat (app/api/chat.py), which
/// resolves tool calls against real data before replying (app/agent/claude_agent.py).
struct ChatView: View {
    @EnvironmentObject private var session: SessionStore
    @StateObject private var viewModel = ChatViewModel()
    @FocusState private var inputFocused: Bool

    var body: some View {
        VStack(spacing: 0) {
            ScrollViewReader { proxy in
                ScrollView {
                    VStack(alignment: .leading, spacing: 12) {
                        if viewModel.messages.isEmpty {
                            emptyState
                        }
                        ForEach(viewModel.messages) { bubble in
                            bubbleView(bubble).id(bubble.id)
                        }
                        if viewModel.isSending {
                            HStack {
                                ProgressView().controlSize(.small)
                                Text("Thinking…").font(.footnote).foregroundStyle(.secondary)
                            }
                        }
                    }
                    .padding()
                }
                .onChange(of: viewModel.messages.count) {
                    if let last = viewModel.messages.last {
                        withAnimation { proxy.scrollTo(last.id, anchor: .bottom) }
                    }
                }
            }

            if let errorMessage = viewModel.errorMessage {
                Text(errorMessage).font(.footnote).foregroundStyle(.red).padding(.horizontal)
            }

            inputBar
        }
        .navigationTitle("Ask Bankr")
        .navigationBarTitleDisplayMode(.inline)
    }

    private var emptyState: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Ask about your money").font(.headline)
            Text("Try \u{201c}how much did I spend on dining this month?\u{201d} or \u{201c}am I on pace for my goal?\u{201d}")
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
        .padding(.vertical, 24)
    }

    private func bubbleView(_ bubble: ChatBubble) -> some View {
        HStack {
            if bubble.role == "user" { Spacer(minLength: 40) }
            Text(bubble.text)
                .padding(.horizontal, 14)
                .padding(.vertical, 10)
                .background(bubble.role == "user" ? Color.accentColor : Color(.secondarySystemBackground))
                .foregroundStyle(bubble.role == "user" ? .white : .primary)
                .clipShape(RoundedRectangle(cornerRadius: 16))
            if bubble.role == "assistant" { Spacer(minLength: 40) }
        }
    }

    private var inputBar: some View {
        HStack(spacing: 8) {
            TextField("Message", text: $viewModel.draft, axis: .vertical)
                .textFieldStyle(.roundedBorder)
                .focused($inputFocused)
                .lineLimit(1...4)
            Button {
                Task { await send() }
            } label: {
                Image(systemName: "arrow.up.circle.fill").font(.title)
            }
            .disabled(viewModel.draft.trimmingCharacters(in: .whitespaces).isEmpty || viewModel.isSending)
        }
        .padding()
    }

    private func send() async {
        guard let token = session.sessionToken else { return }
        await viewModel.send(sessionToken: token)
    }
}

#Preview {
    NavigationStack { ChatView() }
        .environmentObject(SessionStore())
}
