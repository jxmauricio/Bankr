import { useFloatingTabInset } from "@/theme/tabBar";
import { ComingSoon, Screen } from "@/ui";

export default function PlanScreen() {
  const tabInset = useFloatingTabInset();
  return (
    <Screen padded={false} edges={[]} contentStyle={{ paddingBottom: tabInset }}>
      <ComingSoon title="Plan" detail="Your budget, bills and recurring charges. Coming to the app soon." />
    </Screen>
  );
}
