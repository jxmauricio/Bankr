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
    @Published private(set) var errorMessage: String?

    private var conversationId: String?

    func send(sessionToken: String) async {
        let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, !isSending else { return }

        draft = ""
        errorMessage = nil
        messages.append(ChatBubble(role: "user", text: text))
        isSending = true
        defer { isSending = false }

        do {
            let response = try await BankrAPIClient.shared.sendChatMessage(
                text, conversationId: conversationId, sessionToken: sessionToken
            )
            conversationId = response.conversationId
            messages.append(ChatBubble(role: "assistant", text: response.reply))
        } catch {
            errorMessage = "Couldn't reach Bankr. Try again."
        }
    }
}
