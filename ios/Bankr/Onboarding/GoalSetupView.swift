import SwiftUI

private enum GoalType: String, CaseIterable, Identifiable {
    case saveAmount = "save_amount"
    case payOffDebt = "pay_off_debt"
    case buildEmergencyFund = "build_emergency_fund"

    var id: String { rawValue }

    var title: String {
        switch self {
        case .saveAmount: "Save toward a target"
        case .payOffDebt: "Pay off debt"
        case .buildEmergencyFund: "Build an emergency fund"
        }
    }

    var systemImage: String {
        switch self {
        case .saveAmount: "target"
        case .payOffDebt: "creditcard"
        case .buildEmergencyFund: "umbrella"
        }
    }
}

/// The core onboarding differentiator vs. Monarch: a single guided goal,
/// not a budgeting form dump. Posts to `POST /goals` (see backend/app/api/goals.py).
struct GoalSetupView: View {
    let onComplete: () -> Void

    @EnvironmentObject private var session: SessionStore
    @State private var selectedType: GoalType?
    @State private var targetAmountText = ""
    @State private var hasTargetDate = false
    @State private var targetDate = Date().addingTimeInterval(60 * 60 * 24 * 180)
    @State private var isSubmitting = false
    @State private var errorMessage: String?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                VStack(alignment: .leading, spacing: 4) {
                    Text("What are you working toward?")
                        .font(.title2.bold())
                    Text("Bankr will track your progress toward this from your dashboard.")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }

                VStack(spacing: 12) {
                    ForEach(GoalType.allCases) { type in
                        goalTypeCard(type)
                    }
                }

                if selectedType != nil {
                    detailsSection
                }

                if let errorMessage {
                    Text(errorMessage)
                        .font(.footnote)
                        .foregroundStyle(.red)
                }

                if selectedType != nil {
                    Button {
                        Task { await submit() }
                    } label: {
                        if isSubmitting {
                            ProgressView().frame(maxWidth: .infinity)
                        } else {
                            Text("Set Goal").frame(maxWidth: .infinity)
                        }
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.large)
                    .disabled(isSubmitting || !isValid)
                }
            }
            .padding()
        }
    }

    private func goalTypeCard(_ type: GoalType) -> some View {
        Button {
            withAnimation(.snappy) { selectedType = type }
        } label: {
            HStack {
                Image(systemName: type.systemImage)
                    .font(.title3)
                    .frame(width: 32)
                Text(type.title)
                    .font(.body.weight(.medium))
                Spacer()
                if selectedType == type {
                    Image(systemName: "checkmark.circle.fill")
                        .foregroundStyle(.tint)
                }
            }
            .padding()
            .background(selectedType == type ? Color.accentColor.opacity(0.12) : Color(.secondarySystemBackground))
            .clipShape(RoundedRectangle(cornerRadius: 14))
        }
        .buttonStyle(.plain)
    }

    private var detailsSection: some View {
        VStack(alignment: .leading, spacing: 16) {
            VStack(alignment: .leading, spacing: 6) {
                Text("Target amount")
                    .font(.subheadline.weight(.medium))
                TextField("$0", text: $targetAmountText)
                    .keyboardType(.decimalPad)
                    .textFieldStyle(.roundedBorder)
            }

            Toggle("Set a target date", isOn: $hasTargetDate.animation())
            if hasTargetDate {
                DatePicker("Target date", selection: $targetDate, in: Date()..., displayedComponents: .date)
                    .datePickerStyle(.compact)
            }
        }
    }

    private var isValid: Bool {
        guard let amount = Double(targetAmountText) else { return false }
        return amount > 0
    }

    private func submit() async {
        guard let selectedType, let amount = Double(targetAmountText), let token = session.sessionToken else { return }
        isSubmitting = true
        errorMessage = nil
        defer { isSubmitting = false }

        do {
            _ = try await BankrAPIClient.shared.createGoal(
                type: selectedType.rawValue,
                targetAmount: amount,
                targetDate: hasTargetDate ? targetDate : nil,
                sessionToken: token
            )
            onComplete()
        } catch {
            errorMessage = "Couldn't save your goal. Check your connection and try again."
        }
    }
}

#Preview {
    GoalSetupView(onComplete: {})
        .environmentObject(SessionStore())
}
