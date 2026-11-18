import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { KeyboardAvoidingView, Platform, Pressable, StyleSheet, View } from "react-native";
import Animated, {
  Easing,
  SlideInLeft,
  SlideInRight,
  SlideOutLeft,
  SlideOutRight,
  type SharedValue,
  useAnimatedStyle,
  useSharedValue,
  withTiming,
} from "react-native-reanimated";
import {
  ApiError,
  saveFinancialProfile,
  signUp,
  type OnboardingAnswers,
  type OnboardingHousing,
  type OnboardingKnowledge,
  type OnboardingLifestyle,
  type OnboardingOccupation,
} from "@/lib/api";
import { space } from "@/theme/tokens";
import { makeStyles, useColors } from "@/theme/theme";
import { Button, Chip, Icon, IconButton, Screen, Text, TextField, Wordmark } from "@/ui";
import { RecapCarousel } from "./RecapCarousel";
import {
  dollars,
  estimatedNetWorth,
  parseMoney,
  pickInsight,
  pricingPromise,
  roughBudget,
  suggestedGoals,
  type DraftDebt,
  type DraftGoal,
  type DraftInvestment,
} from "./insights";

type Step =
  | "intro"
  | "story"
  | "age"
  | "occupation"
  | "pay"
  | "cash"
  | "emergency"
  | "housing"
  | "housing-amount"
  | "debts"
  | "investments"
  | "goals"
  | "knowledge"
  | "lifestyle"
  | "recap"
  | "pricing"
  | "signup";

type AddPhase = "list" | "pick" | "fields";

const OCCUPATIONS: { id: OnboardingOccupation; label: string; blurb: string }[] = [
  { id: "salaried", label: "Salaried", blurb: "A regular paycheck on a schedule." },
  { id: "contractor", label: "Contractor", blurb: "Income that changes month to month." },
  { id: "student", label: "Student / part-time", blurb: "School first, a side job, or both." },
];

const HOUSING: { id: OnboardingHousing; label: string; blurb: string }[] = [
  { id: "rent", label: "Rent", blurb: "I pay a landlord each month." },
  { id: "mortgage", label: "Mortgage", blurb: "I'm paying down a house." },
  { id: "none", label: "Neither", blurb: "No rent or mortgage right now." },
];

const KNOWLEDGE: { id: OnboardingKnowledge; label: string; blurb: string }[] = [
  { id: "nothing", label: "Nothing", blurb: "Starting from scratch. Keep it plain and explain the why." },
  { id: "somewhat", label: "Somewhat", blurb: "I know the basics — budgets, emergency funds, paying down debt." },
  { id: "expert", label: "Expert", blurb: "I already speak this language. Skip the intro course; be direct." },
];

const LIFESTYLES: { id: OnboardingLifestyle; label: string; blurb: string }[] = [
  { id: "strict", label: "Strict", blurb: "FIRE, high savings rate, invest first. Cut the fat." },
  { id: "balanced", label: "Balanced", blurb: "Save with a plan, still live a little." },
  { id: "ball", label: "Let's Ball Out", blurb: "Sick experiences. Don't lecture me out of the trip." },
];

const DEBT_CHIPS = ["Student loans", "Credit card", "Auto loan", "Medical", "Other"];
const INVESTMENT_CHIPS = ["401(k)", "Roth IRA", "Brokerage", "Crypto", "Other"];
const GOAL_CHIPS = ["Pay off debt", "Trip", "House", "Cushion", "Other"];

/**
 * Questionnaire, recap, then $6.99. Guests create an account on the last step;
 * signed-in users save with their token. Answers become financial_profile.md.
 */
export function Onboarding({
  token = null,
  onDone,
  onExit,
}: {
  token?: string | null;
  onDone: (sessionToken?: string) => void;
  onExit: () => void;
}) {
  const styles = useStyles();
  const [step, setStep] = useState<Step>("intro");
  const [story, setStory] = useState("");
  const [age, setAge] = useState("");
  const [occupation, setOccupation] = useState<OnboardingOccupation | null>(null);
  const [income, setIncome] = useState("");
  const [cashOnHand, setCashOnHand] = useState("");
  const [emergencyFund, setEmergencyFund] = useState("");
  const [housing, setHousing] = useState<OnboardingHousing | null>(null);
  const [housingPay, setHousingPay] = useState("");
  const [debts, setDebts] = useState<DraftDebt[]>([]);
  const [investments, setInvestments] = useState<DraftInvestment[]>([]);
  const [goals, setGoals] = useState<DraftGoal[]>([]);
  const [knowledge, setKnowledge] = useState<OnboardingKnowledge | null>(null);
  const [lifestyle, setLifestyle] = useState<OnboardingLifestyle | null>(null);
  const [addPhase, setAddPhase] = useState<AddPhase>("list");
  const [draftName, setDraftName] = useState("");
  const [draftOther, setDraftOther] = useState(false);
  const [draftOwed, setDraftOwed] = useState("");
  const [draftPaid, setDraftPaid] = useState("");
  const [draftAmount, setDraftAmount] = useState("");
  const [draftTarget, setDraftTarget] = useState("");
  const [draftSaved, setDraftSaved] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [inviteCode, setInviteCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [dir, setDir] = useState<1 | -1>(1);
  const progress = useSharedValue(0);

  const storyPath = Boolean(story.trim()) && !occupation;
  const questionFlow = useMemo<Step[]>(() => {
    const steps: Step[] = ["age", "occupation", "pay", "cash", "emergency", "housing"];
    if (housing && housing !== "none") steps.push("housing-amount");
    steps.push("debts", "investments", "goals", "knowledge", "lifestyle");
    return steps;
  }, [housing]);
  const { current, total, left } = useMemo(() => {
    const i = questionFlow.indexOf(step);
    if (i === -1) return { current: 0, total: questionFlow.length, left: 0 };
    return { current: i + 1, total: questionFlow.length, left: questionFlow.length - i - 1 };
  }, [step, questionFlow]);

  const pay = parseMoney(income);
  const cash = parseMoney(cashOnHand);
  const emergency = parseMoney(emergencyFund);
  const rent = parseMoney(housingPay);
  const insight = useMemo(() => {
    if (!occupation || !lifestyle || !Number.isFinite(pay) || pay <= 0) return null;
    const housingAmount = housing && housing !== "none" && Number.isFinite(rent) ? rent : 0;
    const liquid = cashOnHand.trim() === "" || !Number.isFinite(cash) || cash < 0 ? 0 : cash;
    const fund = emergencyFund.trim() === "" || !Number.isFinite(emergency) || emergency < 0 ? 0 : emergency;
    return {
      budget: roughBudget(pay, lifestyle, debts, housing, housingAmount),
      goals: suggestedGoals(goals, debts, pay, { saved: fund, target: pay * 3 }),
      worth: estimatedNetWorth(investments, debts, liquid, fund),
      pitch: pickInsight({
        occupation,
        income: pay,
        debts,
        investments,
        goals,
        lifestyle,
        housingKind: housing,
        housingPayment: housingAmount,
        cash: liquid,
        emergency: fund,
      }),
      promise: pricingPromise({
        income: pay,
        debts,
        goals,
        housingKind: housing,
        housingPayment: housingAmount,
        emergency: fund,
      }),
    };
  }, [occupation, lifestyle, pay, cash, cashOnHand, emergency, emergencyFund, rent, housing, debts, investments, goals]);

  function resetAdd() {
    setAddPhase("list");
    setDraftName("");
    setDraftOther(false);
    setDraftOwed("");
    setDraftPaid("");
    setDraftAmount("");
    setDraftTarget("");
    setDraftSaved("");
  }

  function go(next: Step, direction: 1 | -1 = 1) {
    setError(null);
    resetAdd();
    setDir(direction);
    setStep(next);
  }

  function back() {
    setError(null);
    if (addPhase !== "list") {
      if (addPhase === "fields") {
        setAddPhase("pick");
        setDraftOwed("");
        setDraftPaid("");
        setDraftAmount("");
        setDraftTarget("");
        setDraftSaved("");
        return;
      }
      resetAdd();
      return;
    }
    if (step === "story") return go("intro", -1);
    if (storyPath && step === "recap") return go("story", -1);
    if (storyPath && step === "pricing") return go("recap", -1);
    if (step === "housing-amount") return go("housing", -1);
    if (step === "debts" && housing === "none") return go("housing", -1);
    const order: Step[] = [
      "intro",
      "age",
      "occupation",
      "pay",
      "cash",
      "emergency",
      "housing",
      "housing-amount",
      "debts",
      "investments",
      "goals",
      "knowledge",
      "lifestyle",
      "recap",
      "pricing",
      "signup",
    ];
    const at = order.indexOf(step);
    if (at > 0) go(order[at - 1], -1);
    else onExit();
  }

  function buildAnswers(): OnboardingAnswers {
    return {
      age: Number(age),
      occupation: occupation!,
      monthly_income: pay,
      cash: cashOnHand.trim() === "" || !Number.isFinite(cash) || cash < 0 ? 0 : cash,
      emergency_fund: emergencyFund.trim() === "" || !Number.isFinite(emergency) || emergency < 0 ? 0 : emergency,
      housing: housing ?? "none",
      housing_payment: housing && housing !== "none" && Number.isFinite(rent) ? rent : 0,
      debts: debts
        .filter((d) => d.name.trim())
        .map((d) => ({ name: d.name.trim(), owed: parseMoney(d.owed) || 0, paid_off: parseMoney(d.paid_off) || 0 })),
      investments: investments
        .filter((i) => i.name.trim())
        .map((i) => ({ name: i.name.trim(), amount: parseMoney(i.amount) || 0 })),
      goals: goals
        .filter((g) => g.name.trim())
        .map((g) => {
          const target = parseMoney(g.target);
          const saved = parseMoney(g.saved);
          return {
            name: g.name.trim(),
            target: Number.isFinite(target) && target > 0 ? target : null,
            saved: Number.isFinite(saved) && saved > 0 ? saved : null,
          };
        }),
      knowledge: knowledge!,
      lifestyle: lifestyle!,
    };
  }

  async function persist(sessionToken: string) {
    if (storyPath) {
      await saveFinancialProfile(sessionToken, { path: "story", story: story.trim() });
    } else {
      await saveFinancialProfile(sessionToken, { path: "questions", answers: buildAnswers() });
    }
  }

  async function finishWithToken(sessionToken: string) {
    setError(null);
    setBusy(true);
    try {
      await persist(sessionToken);
      onDone(sessionToken);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't save that. Try again.");
    } finally {
      setBusy(false);
    }
  }

  function afterPricing() {
    if (token) return finishWithToken(token);
    go("signup");
  }

  async function createAccount() {
    if (!email.trim() || password.length < 8) {
      setError("Email and an 8+ character password.");
      return;
    }
    setError(null);
    setBusy(true);
    try {
      const response = await signUp(email.trim(), password, inviteCode.trim());
      await persist(response.session_token);
      onDone(response.session_token);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't create that account. Try again.");
    } finally {
      setBusy(false);
    }
  }

  const footer = (label: string, onPress: () => void) => (
    <View style={styles.footer}>
      {error ? (
        <Text variant="caption" tone="negative" accessibilityRole="alert">
          {error}
        </Text>
      ) : null}
      <Button label={label} onPress={onPress} loading={busy} />
    </View>
  );

  function chrome(title: string, subtitle?: string) {
    const counting = current > 0;
    return (
      <View style={styles.head}>
        {counting ? <ProgressBar fraction={current / total} value={progress} /> : null}
        <View style={styles.bar}>
          <IconButton icon="chevronLeft" label="Back" variant="plain" onPress={back} />
          {counting ? (
            <>
              <Text variant="caption" accessibilityLabel={`Step ${current} of ${total}`}>
                {current} of {total}
              </Text>
              <View style={styles.barGrow} />
              <Text variant="caption" tone="soft">
                {left === 0 ? "Last step" : `${left} left`}
              </Text>
            </>
          ) : (
            <View style={styles.barGrow} />
          )}
        </View>
        <Text variant="display">{title}</Text>
        {subtitle ? <Text tone="soft">{subtitle}</Text> : null}
      </View>
    );
  }

  function addFooter(hasItems: boolean, onAdd: () => void, onContinue: () => void, addLabel: string) {
    return (
      <View style={styles.footer}>
        {error ? (
          <Text variant="caption" tone="negative" accessibilityRole="alert">
            {error}
          </Text>
        ) : null}
        <Button label={addLabel} variant={hasItems ? "secondary" : "primary"} onPress={onAdd} />
        <Button label="Continue" variant={hasItems ? "primary" : "secondary"} onPress={onContinue} />
      </View>
    );
  }

  if (step === "intro") {
    return (
      <Board step={step} dir={dir}>
        <View style={styles.hero}>
          <Wordmark />
          <Text variant="display">A few questions about your money.</Text>
          <Text tone="soft">
            We'll use them to personalize your account — budgets, goals, and how Centsio talks to you.
          </Text>
        </View>
        <View style={styles.footer}>
          <Button label="Answer a few questions" onPress={() => go("age")} />
          <Button label="Talk to Centsio in chat" variant="secondary" onPress={() => go("story")} />
          <Button label={token ? "Sign out" : "Back"} variant="ghost" onPress={onExit} />
        </View>
      </Board>
    );
  }

  if (step === "story") {
    return (
      <Board step={step} dir={dir}>
        {chrome("Talk to Centsio", "Explain your situation in your own words.")}
        <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={styles.fill}>
          <TextField
            value={story}
            onChangeText={setStory}
            placeholder="I freelance, have student loans, want a house in a few years…"
            multiline
            style={styles.story}
          />
          {footer("Continue", () => {
            if (story.trim().length < 8) {
              setError("Write a bit more about what's going on.");
              return;
            }
            go("recap");
          })}
        </KeyboardAvoidingView>
      </Board>
    );
  }

  if (step === "age") {
    return (
      <Board step={step} dir={dir}>
        {chrome("Age")}
        <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={styles.fill}>
          <TextField value={age} onChangeText={setAge} keyboardType="number-pad" placeholder="Years" autoFocus />
          {footer("Continue", () => {
            const years = Number(age);
            if (!Number.isInteger(years) || years < 16 || years > 120) {
              setError("Enter your age.");
              return;
            }
            go("occupation");
          })}
        </KeyboardAvoidingView>
      </Board>
    );
  }

  if (step === "occupation") {
    return (
      <Board step={step} dir={dir}>
        {chrome("How you earn")}
        <View style={styles.stack}>
          {OCCUPATIONS.map((o) => (
            <Choice key={o.id} label={o.label} blurb={o.blurb} on={occupation === o.id} onPress={() => setOccupation(o.id)} />
          ))}
        </View>
        {footer("Continue", () => {
          if (!occupation) {
            setError("Pick how you earn.");
            return;
          }
          go("pay");
        })}
      </Board>
    );
  }

  if (step === "pay") {
    return (
      <Board step={step} dir={dir}>
        {chrome("How Much Do You Make A Month?", "Take-home, not gross.")}
        <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={styles.fill}>
          <TextField value={income} onChangeText={setIncome} keyboardType="decimal-pad" placeholder="0" autoFocus />
          {footer("Continue", () => {
            if (!Number.isFinite(pay) || pay <= 0) {
              setError("Enter what you usually make in a month.");
              return;
            }
            go("cash");
          })}
        </KeyboardAvoidingView>
      </Board>
    );
  }

  if (step === "cash") {
    return (
      <Board step={step} dir={dir}>
        {chrome("How much cash do you have right now?", "Everyday money you spend from — not an emergency fund. We'll ask about that next.")}
        <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={styles.fill}>
          <TextField value={cashOnHand} onChangeText={setCashOnHand} keyboardType="decimal-pad" placeholder="0" autoFocus />
          {footer("Continue", () => {
            if (cashOnHand.trim() === "" || !Number.isFinite(cash) || cash < 0) {
              setError("Enter how much cash you have, even if it's zero.");
              return;
            }
            go("emergency");
          })}
        </KeyboardAvoidingView>
      </Board>
    );
  }

  if (step === "emergency") {
    return (
      <Board step={step} dir={dir}>
        {chrome("Emergency fund", "A stash for surprises, separate from spending cash. Continue if you don't have one.")}
        <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={styles.fill}>
          <TextField
            value={emergencyFund}
            onChangeText={setEmergencyFund}
            keyboardType="decimal-pad"
            placeholder="0"
            autoFocus
          />
          {footer("Continue", () => {
            if (emergencyFund.trim() !== "" && (!Number.isFinite(emergency) || emergency < 0)) {
              setError("Enter how much is in the fund, or leave it blank.");
              return;
            }
            go("housing");
          })}
        </KeyboardAvoidingView>
      </Board>
    );
  }

  if (step === "housing") {
    return (
      <Board step={step} dir={dir}>
        {chrome("Rent or mortgage?")}
        <View style={styles.stack}>
          {HOUSING.map((h) => (
            <Choice key={h.id} label={h.label} blurb={h.blurb} on={housing === h.id} onPress={() => setHousing(h.id)} />
          ))}
        </View>
        {footer("Continue", () => {
          if (!housing) {
            setError("Pick one.");
            return;
          }
          go(housing === "none" ? "debts" : "housing-amount");
        })}
      </Board>
    );
  }

  if (step === "housing-amount") {
    return (
      <Board step={step} dir={dir}>
        {chrome(housing === "mortgage" ? "How much is the mortgage a month?" : "How much is rent a month?")}
        <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={styles.fill}>
          <TextField value={housingPay} onChangeText={setHousingPay} keyboardType="decimal-pad" placeholder="0" autoFocus />
          {footer("Continue", () => {
            if (!Number.isFinite(rent) || rent <= 0) {
              setError("Enter the monthly amount.");
              return;
            }
            go("debts");
          })}
        </KeyboardAvoidingView>
      </Board>
    );
  }

  if (step === "debts") {
    return (
      <Board step={step} dir={dir} scroll>
        {chrome("Payments and debts", "Add each one. Continue if you don't have any.")}
        {debts.length === 0 ? (
          <Example title="Student loans" detail="$12,000 owed, $6,000 paid off" />
        ) : (
          <View style={styles.stack}>
            {debts.map((row, i) => (
              <Listed
                key={`${row.name}-${i}`}
                title={row.name}
                detail={debtDetail(row)}
                onRemove={() => setDebts(debts.filter((_, j) => j !== i))}
              />
            ))}
          </View>
        )}
        {addPhase === "pick" ? (
          <View style={styles.picker}>
            <Text variant="caption" tone="soft">
              What kind?
            </Text>
            <View style={styles.wrap}>
              {DEBT_CHIPS.map((label) => (
                <Chip
                  key={label}
                  label={label}
                  onPress={() => {
                    const other = label === "Other";
                    setDraftOther(other);
                    setDraftName(other ? "" : label);
                    setAddPhase("fields");
                  }}
                />
              ))}
            </View>
          </View>
        ) : null}
        {addPhase === "fields" ? (
          <View style={styles.picker}>
            {draftOther ? (
              <TextField label="Name" value={draftName} onChangeText={setDraftName} placeholder="What is it?" />
            ) : (
              <Text variant="strong">{draftName}</Text>
            )}
            <TextField label="Still owed" value={draftOwed} onChangeText={setDraftOwed} keyboardType="decimal-pad" placeholder="0" />
            <TextField label="Already paid off" value={draftPaid} onChangeText={setDraftPaid} keyboardType="decimal-pad" placeholder="0" />
            <Button
              label="Add"
              onPress={() => {
                const name = draftName.trim();
                if (!name) {
                  setError("Name the debt.");
                  return;
                }
                setError(null);
                setDebts([...debts, { name, owed: draftOwed, paid_off: draftPaid }]);
                resetAdd();
              }}
            />
          </View>
        ) : null}
        {addPhase === "list"
          ? addFooter(debts.length > 0, () => setAddPhase("pick"), () => go("investments"), debts.length ? "Add another" : "Add")
          : (
            <View style={styles.footer}>
              <Button label="Continue" variant={debts.length > 0 ? "primary" : "secondary"} onPress={() => go("investments")} />
            </View>
          )}
      </Board>
    );
  }

  if (step === "investments") {
    return (
      <Board step={step} dir={dir} scroll>
        {chrome("Investments", "Add each account. Continue if you don't have any yet.")}
        {investments.length === 0 ? (
          <Example title="401(k)" detail="$8,400" />
        ) : (
          <View style={styles.stack}>
            {investments.map((row, i) => (
              <Listed
                key={`${row.name}-${i}`}
                title={row.name}
                detail={dollars(parseMoney(row.amount) || 0)}
                onRemove={() => setInvestments(investments.filter((_, j) => j !== i))}
              />
            ))}
          </View>
        )}
        {addPhase === "pick" ? (
          <View style={styles.picker}>
            <Text variant="caption" tone="soft">
              What kind?
            </Text>
            <View style={styles.wrap}>
              {INVESTMENT_CHIPS.map((label) => (
                <Chip
                  key={label}
                  label={label}
                  onPress={() => {
                    const other = label === "Other";
                    setDraftOther(other);
                    setDraftName(other ? "" : label);
                    setAddPhase("fields");
                  }}
                />
              ))}
            </View>
          </View>
        ) : null}
        {addPhase === "fields" ? (
          <View style={styles.picker}>
            {draftOther ? (
              <TextField label="Name" value={draftName} onChangeText={setDraftName} placeholder="What is it?" />
            ) : (
              <Text variant="strong">{draftName}</Text>
            )}
            <TextField label="Amount" value={draftAmount} onChangeText={setDraftAmount} keyboardType="decimal-pad" placeholder="0" />
            <Button
              label="Add"
              onPress={() => {
                const name = draftName.trim();
                if (!name) {
                  setError("Name the account.");
                  return;
                }
                setError(null);
                setInvestments([...investments, { name, amount: draftAmount }]);
                resetAdd();
              }}
            />
          </View>
        ) : null}
        {addPhase === "list"
          ? addFooter(investments.length > 0, () => setAddPhase("pick"), () => go("goals"), investments.length ? "Add another" : "Add")
          : (
            <View style={styles.footer}>
              <Button label="Continue" variant={investments.length > 0 ? "primary" : "secondary"} onPress={() => go("goals")} />
            </View>
          )}
      </Board>
    );
  }

  if (step === "goals") {
    return (
      <Board step={step} dir={dir} scroll>
        {chrome("Goals", "Add as many as you want, and how much you've already put toward them. Continue if you're not sure yet.")}
        {goals.length === 0 ? (
          <Example title="Trip" detail="$3,200 of $8,000" />
        ) : (
          <View style={styles.stack}>
            {goals.map((row, i) => (
              <Listed
                key={`${row.name}-${i}`}
                title={row.name}
                detail={goalDetail(row)}
                onRemove={() => setGoals(goals.filter((_, j) => j !== i))}
              />
            ))}
          </View>
        )}
        {addPhase === "pick" ? (
          <View style={styles.picker}>
            <Text variant="caption" tone="soft">
              What kind?
            </Text>
            <View style={styles.wrap}>
              {GOAL_CHIPS.map((label) => (
                <Chip
                  key={label}
                  label={label}
                  onPress={() => {
                    const other = label === "Other";
                    setDraftOther(other);
                    setDraftName(other ? "" : label);
                    setAddPhase("fields");
                  }}
                />
              ))}
            </View>
          </View>
        ) : null}
        {addPhase === "fields" ? (
          <View style={styles.picker}>
            {draftOther ? (
              <TextField label="Name" value={draftName} onChangeText={setDraftName} placeholder="What is it?" />
            ) : (
              <Text variant="strong">{draftName}</Text>
            )}
            <TextField
              label="Target (optional)"
              value={draftTarget}
              onChangeText={setDraftTarget}
              keyboardType="decimal-pad"
              placeholder="0"
            />
            <TextField
              label="Already put toward it"
              value={draftSaved}
              onChangeText={setDraftSaved}
              keyboardType="decimal-pad"
              placeholder="0"
            />
            <Button
              label="Add"
              onPress={() => {
                const name = draftName.trim();
                if (!name) {
                  setError("Name the goal.");
                  return;
                }
                setError(null);
                setGoals([...goals, { name, target: draftTarget, saved: draftSaved }]);
                resetAdd();
              }}
            />
          </View>
        ) : null}
        {addPhase === "list"
          ? addFooter(goals.length > 0, () => setAddPhase("pick"), () => go("knowledge"), goals.length ? "Add another" : "Add")
          : (
            <View style={styles.footer}>
              <Button label="Continue" variant={goals.length > 0 ? "primary" : "secondary"} onPress={() => go("knowledge")} />
            </View>
          )}
      </Board>
    );
  }

  if (step === "knowledge") {
    return (
      <Board step={step} dir={dir}>
        {chrome("Personal finance", "How much do you already know?")}
        <View style={styles.stack}>
          {KNOWLEDGE.map((k) => (
            <Choice key={k.id} label={k.label} blurb={k.blurb} on={knowledge === k.id} onPress={() => setKnowledge(k.id)} />
          ))}
        </View>
        {footer("Continue", () => {
          if (!knowledge) {
            setError("Pick one.");
            return;
          }
          go("lifestyle");
        })}
      </Board>
    );
  }

  if (step === "lifestyle") {
    return (
      <Board step={step} dir={dir}>
        {chrome("Balance", "How do you want to live with the money?")}
        <View style={styles.stack}>
          {LIFESTYLES.map((k) => (
            <Choice key={k.id} label={k.label} blurb={k.blurb} on={lifestyle === k.id} onPress={() => setLifestyle(k.id)} />
          ))}
        </View>
        {footer("Continue", () => {
          if (!lifestyle) {
            setError("Pick one.");
            return;
          }
          go("recap");
        })}
      </Board>
    );
  }

  if (step === "recap") {
    const pitch = insight?.pitch ?? {
      title: "We'll start from your note.",
      body: "Centsio will read what you wrote first, every time you ask — then we'll fill in the rest once a bank is linked.",
      cta: "Centsio will keep that picture in front of the advice.",
    };
    return (
      <Board step={step} dir={dir}>
        {chrome("Here's what we see")}
        <RecapCarousel
          budget={insight?.budget ?? null}
          goals={insight?.goals ?? []}
          worth={insight?.worth ?? null}
          pitch={pitch}
          onContinue={() => go("pricing")}
        />
      </Board>
    );
  }

  if (step === "signup") {
    return (
      <Board step={step} dir={dir}>
        {chrome("Create your account")}
        <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={styles.fill}>
          <TextField
            label="Email"
            value={email}
            onChangeText={setEmail}
            autoCapitalize="none"
            autoComplete="email"
            keyboardType="email-address"
            textContentType="emailAddress"
            placeholder="you@example.com"
          />
          <TextField
            label="Password"
            value={password}
            onChangeText={setPassword}
            secureTextEntry
            autoComplete="new-password"
            textContentType="newPassword"
          />
          <TextField label="Invite code" value={inviteCode} onChangeText={setInviteCode} autoCapitalize="none" />
          {footer(busy ? "Creating…" : "Create account", createAccount)}
        </KeyboardAvoidingView>
      </Board>
    );
  }

  const promise = insight?.promise ?? [
    { text: "Centsio will help you from what you wrote — budget, goals, and the next move." },
  ];
  return (
    <Board step={step} dir={dir}>
      <View style={styles.hero}>
        <Wordmark />
        <Text variant="display">$6.99 a month</Text>
        <Text>
          {promise.map((part, i) => (
            <Text key={i} variant={part.strong ? "strong" : "body"}>
              {part.text}
            </Text>
          ))}
        </Text>
        <Text variant="caption" tone="soft">
          Press 'Get Started'. We won't actually charge you lol. But in the future, this will go to John's hiking gear and TJ's gambling addiction.
        </Text>
      </View>
      <View style={styles.footer}>
        {error ? (
          <Text variant="caption" tone="negative" accessibilityRole="alert">
            {error}
          </Text>
        ) : null}
        <Button label={busy ? "Saving…" : "Get started"} onPress={afterPricing} loading={busy} />
        <Button label="Back" variant="ghost" onPress={back} />
      </View>
    </Board>
  );
}

function ProgressBar({ fraction, value }: { fraction: number; value: SharedValue<number> }) {
  const styles = useStyles();
  const clamped = Math.min(1, Math.max(0, fraction));
  useEffect(() => {
    value.set(withTiming(clamped, { duration: 420, easing: Easing.out(Easing.cubic) }));
  }, [clamped, value]);
  const fill = useAnimatedStyle(() => ({ width: `${value.get() * 100}%` }));
  return (
    <View
      accessibilityRole="progressbar"
      accessibilityLabel="Onboarding progress"
      accessibilityValue={{ min: 0, max: 100, now: Math.round(clamped * 100) }}
      style={styles.progressTrack}
    >
      <Animated.View style={[styles.progressFill, fill]} />
    </View>
  );
}

function Board({
  step,
  dir,
  scroll,
  children,
}: {
  step: Step;
  dir: number;
  scroll?: boolean;
  children: ReactNode;
}) {
  return (
    <Screen edges={["top", "bottom"]} scroll={scroll} contentStyle={stylesClip}>
      <SlideFrame step={step} dir={dir} fill={!scroll}>
        {children}
      </SlideFrame>
    </Screen>
  );
}

const stylesClip = { overflow: "hidden" as const, flexGrow: 1 };

function SlideFrame({
  step,
  dir,
  fill,
  children,
}: {
  step: string;
  dir: number;
  fill?: boolean;
  children: ReactNode;
}) {
  const skip = useRef(true);
  const ease = Easing.out(Easing.cubic);
  const entering = skip.current
    ? undefined
    : dir >= 0
      ? SlideInRight.duration(340).easing(ease)
      : SlideInLeft.duration(340).easing(ease);
  if (skip.current) skip.current = false;
  const exiting = dir >= 0 ? SlideOutLeft.duration(280).easing(ease) : SlideOutRight.duration(280).easing(ease);
  return (
    <Animated.View key={step} entering={entering} exiting={exiting} style={fill ? { flex: 1 } : undefined}>
      {children}
    </Animated.View>
  );
}

function Choice({ label, blurb, on, onPress }: { label: string; blurb: string; on: boolean; onPress: () => void }) {
  const styles = useStyles();
  const colors = useColors();
  return (
    <Pressable
      accessibilityRole="radio"
      accessibilityState={{ checked: on }}
      onPress={onPress}
      style={({ pressed }) => [styles.choice, on && styles.choiceOn, pressed && styles.pressed]}
    >
      <View style={styles.choiceText}>
        <Text variant="strong">{label}</Text>
        <Text variant="caption" tone="soft">
          {blurb}
        </Text>
      </View>
      {on ? <Icon name="check" size={18} color={colors.accent} /> : null}
    </Pressable>
  );
}

function debtDetail(row: DraftDebt): string {
  const owed = dollars(parseMoney(row.owed) || 0);
  const paid = parseMoney(row.paid_off);
  if (Number.isFinite(paid) && paid > 0) return `${owed} owed, ${dollars(paid)} paid off`;
  return `${owed} owed`;
}

function goalDetail(row: DraftGoal): string {
  const target = parseMoney(row.target);
  const saved = parseMoney(row.saved);
  if (target > 0 && saved > 0) return `${dollars(saved)} of ${dollars(target)}`;
  if (target > 0) return dollars(target);
  if (saved > 0) return `${dollars(saved)} in so far`;
  return "No target yet";
}

function Listed({ title, detail, onRemove }: { title: string; detail: string; onRemove: () => void }) {
  const styles = useStyles();
  return (
    <View style={styles.listed}>
      <View style={styles.choiceText}>
        <Text variant="strong">{title}</Text>
        <Text variant="caption" tone="soft">
          {detail}
        </Text>
      </View>
      <IconButton icon="close" label="Remove" variant="plain" onPress={onRemove} />
    </View>
  );
}

function Example({ title, detail }: { title: string; detail: string }) {
  const styles = useStyles();
  return (
    <View style={styles.example} accessibilityLabel={`Example, ${title}, ${detail}`}>
      <Text variant="caption" tone="faint">
        Example
      </Text>
      <Text variant="strong" tone="soft">
        {title}
      </Text>
      <Text variant="caption" tone="faint">
        {detail}
      </Text>
    </View>
  );
}

const useStyles = makeStyles((colors) =>
  StyleSheet.create({
    fill: { flex: 1, gap: space.md },
    hero: { flex: 1, justifyContent: "center", gap: space.sm },
    stack: { gap: space.sm },
    wrap: { flexDirection: "row", flexWrap: "wrap", gap: space.sm },
    footer: { gap: space.sm, marginTop: "auto" },
    head: { gap: space.sm, marginBottom: space.sm },
    bar: { flexDirection: "row", alignItems: "center", gap: space.sm, minHeight: 44 },
    barGrow: { flex: 1 },
    progressTrack: { height: 4, width: "100%", backgroundColor: colors.lineStrong, overflow: "hidden" },
    progressFill: { height: 4, backgroundColor: colors.accent },
    story: { minHeight: 160, textAlignVertical: "top" },
    choice: {
      flexDirection: "row",
      alignItems: "center",
      gap: space.md,
      paddingVertical: space.md,
      paddingHorizontal: space.md,
      borderWidth: 1,
      borderColor: colors.lineStrong,
      borderRadius: 0,
    },
    choiceOn: { borderColor: colors.ink, backgroundColor: colors.accentWash },
    choiceText: { flex: 1, gap: 4 },
    listed: {
      flexDirection: "row",
      alignItems: "center",
      paddingVertical: space.sm,
      borderBottomWidth: StyleSheet.hairlineWidth,
      borderBottomColor: colors.line,
    },
    example: {
      gap: 4,
      paddingVertical: space.md,
      opacity: 0.7,
      borderBottomWidth: StyleSheet.hairlineWidth,
      borderBottomColor: colors.line,
    },
    picker: { gap: space.sm, paddingTop: space.md },
    pressed: { opacity: 0.7 },
  })
);
