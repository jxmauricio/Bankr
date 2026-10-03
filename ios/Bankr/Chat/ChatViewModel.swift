import Foundation

struct ChatBubble: Identifiable {
    let id = UUID()
    let role: String  // "user" | "assistant"
    let text: String
}

@MainActor
final class ChatViewModel: ObservableObject {
    @Published private(set) var messages: [ChatBubble] = []
    @Published var draft = ""
    @Published private(set) var isSending = false
    /// Latest progress line from the streaming endpoint, nil until the first
    /// tool runs ("Looking up Dining spending…").
    @Published private(set) var statusLabel: String?
    @Published private(set) var errorMessage: String?

    private var conversationId: String?

    func send(sessionToken: String) async {
        let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, !isSending else { return }

        draft = ""
        errorMessage = nil
        messages.append(ChatBubble(role: "user", text: text))
        isSending = true
        statusLabel = nil
        defer {
            isSending = false
            statusLabel = nil
        }

        do {
            let response = try await BankrAPIClient.shared.streamChatMessage(
                text, conversationId: conversationId, sessionToken: sessionToken
            ) { [weak self] label in
                self?.statusLabel = label
            }
            conversationId = response.conversationId
            messages.append(ChatBubble(role: "assistant", text: response.reply))
        } catch {
            errorMessage = "Couldn't reach Bankr. Try again."
        }
    }
}
