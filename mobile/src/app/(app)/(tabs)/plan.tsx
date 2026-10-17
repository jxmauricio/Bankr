import { AppHeader } from "@/features/money/AppHeader";
import { ComingSoon, Screen } from "@/ui";

export default function PlanScreen() {
  return (
    <Screen padded={false}>
      <AppHeader />
      <ComingSoon title="Plan" detail="Your budget, bills and recurring charges. Coming to the app soon." />
    </Screen>
  );
}
