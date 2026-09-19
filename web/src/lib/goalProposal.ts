import type { GoalProposal } from "./api";

/**
 * The API already resolves the proposal for a message server-side (the
 * agent's most recent propose_goal call, if any). This wrapper exists so
 * the call site reads like a decision rather than a field access, and is
 * the one place to extend if client-side filtering is ever needed.
 */
export function resolveGoalProposal({
  apiProposal,
}: {
  userText: string;
  assistantText: string;
  apiProposal: GoalProposal | null;
}): GoalProposal | null {
  return apiProposal ?? null;
}
