import { AppHeader } from "@/features/money/AppHeader";
import { ComingSoon, Screen } from "@/ui";

export default function HealthScreen() {
  return (
    <Screen padded={false}>
      <AppHeader />
      <ComingSoon title="Health" detail="How your spending compares with your income and your usual months. Coming to the app soon." />
    </Screen>
  );
}
