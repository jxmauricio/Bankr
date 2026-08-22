import LinkKit
import SwiftUI

/// Onboarding step 3 (before goal setup, per the plan): launches Plaid Link
/// so the user's first goal can be seeded from their real starting balance
/// instead of $0. Flow: fetch a link token from our backend -> launch Plaid
/// Link -> on success, hand the resulting public token back to our backend,
/// which exchanges it server-side and runs the first sync (see
/// backend/app/api/accounts.py). The app never sees a Plaid access token.
///
/// API usage (LinkTokenConfiguration / Plaid.createPlaidLinkSession /
/// session.sheet()) is verified against LinkKit 7.1.0's own SwiftUI demo
/// (plaid/plaid-link-ios, LinkDemo-SwiftUI/.../PlaidLinkSessionExampleView.swift),
/// not guessed.
private enum LinkStage {
    case fetchingToken
    case ready
    case linking
    case error(String)
}

struct LinkBankAccountView: View {
    let onComplete: () -> Void

    @EnvironmentObject private var session: SessionStore
    @State private var stage: LinkStage = .fetchingToken
    @State private var linkSession: PlaidLinkSession?
    @State private var isPresentingLink = false

    var body: some View {
        VStack(spacing: 20) {
            Spacer()

            VStack(spacing: 8) {
                Image(systemName: "building.columns")
                    .font(.system(size: 40))
                    .foregroundStyle(.tint)
                Text("Link your bank")
                    .font(.title2.bold())
                Text("Bankr reads your balances and transactions to build your dashboard and track your goal.")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 32)
            }

            if case .error(let message) = stage {
                Text(message)
                    .font(.footnote)
                    .foregroundStyle(.red)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 32)
            }

            Button {
                isPresentingLink = true
            } label: {
                HStack {
                    if isBusy { ProgressView().tint(.white) }
                    Text("Connect a bank account")
                }
                .frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
            .padding(.horizontal, 32)
            .disabled(linkSession == nil || isBusy)

            Spacer()
            Spacer()
        }
        .task { await fetchLinkToken() }
        .sheet(isPresented: $isPresentingLink) {
            linkSession?.sheet()
        }
    }

    private var isBusy: Bool {
        switch stage {
        case .fetchingToken, .linking: true
        default: false
        }
    }

    private func fetchLinkToken() async {
        guard let token = session.sessionToken else { return }
        do {
            let response = try await BankrAPIClient.shared.fetchLinkToken(sessionToken: token)
            buildSession(linkToken: response.linkToken)
        } catch {
            stage = .error("Couldn't start bank linking. Check your connection and try again.")
        }
    }

    private func buildSession(linkToken: String) {
        let configuration = LinkTokenConfiguration(
            token: linkToken,
            onSuccess: { linkSuccess in
                isPresentingLink = false
                Task { await exchangePublicToken(linkSuccess.publicToken) }
            },
            onExit: { linkExit in
                isPresentingLink = false
                if let error = linkExit.error {
                    stage = .error(error.displayMessage ?? "Bank linking was interrupted. Try again.")
                }
            },
            onEvent: nil,
            onLoad: nil
        )

        do {
            linkSession = try Plaid.createPlaidLinkSession(configuration: configuration)
            stage = .ready
        } catch {
            stage = .error("Couldn't prepare bank linking: \(error.localizedDescription)")
        }
    }

    private func exchangePublicToken(_ publicToken: String) async {
        guard let token = session.sessionToken else { return }
        stage = .linking
        do {
            _ = try await BankrAPIClient.shared.linkAccount(publicToken: publicToken, sessionToken: token)
            onComplete()
        } catch {
            stage = .error("Linked, but syncing failed. Pull to retry from the dashboard.")
            onComplete()  // account is linked server-side even if this sync attempt failed; don't strand the user here
        }
    }
}

#Preview {
    LinkBankAccountView(onComplete: {})
        .environmentObject(SessionStore())
}
