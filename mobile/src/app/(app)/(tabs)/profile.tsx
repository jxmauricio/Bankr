import { useState } from "react";
import { Alert, Pressable, RefreshControl, ScrollView, StyleSheet, View } from "react-native";
import { BankLogo } from "@/features/bank/BankLogos";
import { useLinkBank } from "@/features/bank/useLinkBank";
import { useMoney } from "@/features/money/MoneyContext";
import { PushSettings } from "@/features/notifications/PushSettings";
import { ApiError, deleteAccount, disconnectBank, fetchLinkedBanks, fetchProfile, type LinkedBank } from "@/lib/api";
import { useResource } from "@/lib/useResource";
import { useSession, useToken } from "@/lib/session";
import { useFloatingTabInset } from "@/theme/tabBar";
import { useAppearancePref, type AppearancePref } from "@/theme/appearance";
import { space } from "@/theme/tokens";
import { makeStyles, useColors } from "@/theme/theme";
import { Button, Card, Screen, SegmentedControl, Text, TextField } from "@/ui";

const APPEARANCE_OPTIONS: { value: AppearancePref; label: string }[] = [
  { value: "system", label: "System" },
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
];

const ACCOUNT_TYPE_LABELS: Record<string, string> = {
  checking: "Checking",
  savings: "Savings",
  credit: "Credit card",
  loan: "Loan",
  investment: "Investment",
};

function describeAccounts(accounts: LinkedBank["accounts"]) {
  const kinds = new Set(accounts.map((a) => ACCOUNT_TYPE_LABELS[a.account_type] ?? a.account_type));
  return [...kinds].join(" · ");
}

/**
 * Account, banks, appearance, notifications, sign out, and delete. The
 * rightmost tab; settings used to live behind the top-bar gear.
 */
export default function ProfileScreen() {
  const styles = useStyles();
  const colors = useColors();
  const tabInset = useFloatingTabInset();
  const token = useToken();
  const { signOut } = useSession();
  const { banksChanged, syncFromBank, isSyncing, syncVersion } = useMoney();
  const profile = useResource(fetchProfile, []);
  const banks = useResource(fetchLinkedBanks, [syncVersion]);
  const linking = useLinkBank(banksChanged);
  const [appearance, setAppearance] = useAppearancePref();
  const [busyBankId, setBusyBankId] = useState<string | null>(null);
  const [bankError, setBankError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [password, setPassword] = useState("");
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  async function unlink(bank: LinkedBank) {
    setBusyBankId(bank.id);
    setBankError(null);
    try {
      await disconnectBank(token, bank.id);
      await banksChanged();
    } catch (err) {
      setBankError(err instanceof ApiError ? err.message : "Couldn't disconnect this bank. Try again.");
    } finally {
      setBusyBankId(null);
    }
  }

  function confirmUnlink(bank: LinkedBank) {
    Alert.alert(
      "Disconnect this bank?",
      `This removes ${bank.institution_name} and its transactions from Centsio. You can link it again later.`,
      [
        { text: "Cancel", style: "cancel" },
        { text: "Disconnect", style: "destructive", onPress: () => unlink(bank) },
      ]
    );
  }

  async function confirmDelete() {
    setDeleteError(null);
    setIsDeleting(true);
    try {
      await deleteAccount(token, password);
      signOut();
    } catch (err) {
      setDeleteError(err instanceof ApiError ? err.message : "Couldn't delete your account. Try again.");
      setIsDeleting(false);
    }
  }

  return (
    <Screen padded={false} edges={[]}>
      <ScrollView
        contentContainerStyle={[styles.content, { paddingBottom: tabInset + space.md }]}
        refreshControl={<RefreshControl refreshing={isSyncing} onRefresh={syncFromBank} tintColor={colors.accent} />}
        keyboardShouldPersistTaps="handled"
      >
        <Card>
          <Text variant="caption" tone="soft">
            Signed in as
          </Text>
          <Text variant="heading">{profile.data?.email ?? "—"}</Text>
        </Card>

        <Card>
          <Text variant="heading">Appearance</Text>
          <SegmentedControl label="Appearance" options={APPEARANCE_OPTIONS} value={appearance} onChange={setAppearance} />
          <Text variant="meta" tone="faint">
            Light and dark match the web app. The sun/moon in the top bar switches them; System follows the phone.
          </Text>
        </Card>

        <Card>
          <Text variant="heading">Notifications</Text>
          <PushSettings embedded />
        </Card>

        <Card>
          <Text variant="heading">Connected banks</Text>
          <Text variant="meta" tone="faint">
            Centsio reads these through Plaid. Disconnecting removes that bank and its transactions; you can link it again later.
          </Text>
          {banks.status === "error" && !banks.data && (
            <Text variant="caption" tone="negative">
              {banks.error}
            </Text>
          )}
          {banks.data?.length === 0 && (
            <Text variant="meta" tone="faint">
              No banks connected.
            </Text>
          )}
          {banks.data?.map((bank) => (
            <View key={bank.id} style={styles.bank}>
              <BankLogo name={bank.institution_name} />
              <View style={styles.flex}>
                <Text numberOfLines={1}>{bank.institution_name}</Text>
                <Text variant="meta" tone="faint">
                  {describeAccounts(bank.accounts)}
                </Text>
                {bank.status === "error" && (
                  <Text variant="caption" tone="negative">
                    Needs attention: sign in to this bank again.
                  </Text>
                )}
              </View>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel={`Disconnect ${bank.institution_name}`}
                disabled={busyBankId !== null || isDeleting || linking.busy}
                onPress={() => confirmUnlink(bank)}
                hitSlop={8}
                style={({ pressed }) => [pressed && styles.pressed]}
              >
                <Text variant="label" tone="negative">
                  {busyBankId === bank.id ? "…" : "Disconnect"}
                </Text>
              </Pressable>
            </View>
          ))}
          {bankError && (
            <Text variant="caption" tone="negative" accessibilityRole="alert">
              {bankError}
            </Text>
          )}
          {linking.error && (
            <Text variant="caption" tone="negative" accessibilityRole="alert">
              {linking.error}
            </Text>
          )}
          <Button label="Link another bank" variant="secondary" onPress={linking.link} loading={linking.busy} />
        </Card>

        <Card>
          <Text variant="heading">Privacy</Text>
          <Text variant="meta" tone="faint">
            Centsio is read-only: it never moves money. Chat memory, categories and rules stay on our servers until you delete them
            or this account.
          </Text>
        </Card>

        <View style={styles.signOut}>
          <Button label="Sign out" variant="secondary" onPress={signOut} />
        </View>

        <Card>
          <Text variant="heading">Delete account</Text>
          {!deleting ? (
            <>
              <Text variant="meta" tone="faint">
                Permanently deletes your Centsio account, goals, chat history and every connected bank.
              </Text>
              <Button label="Delete my account…" variant="danger" onPress={() => setDeleting(true)} disabled={isDeleting} />
            </>
          ) : (
            <>
              <Text tone="soft">This can't be undone. Enter your password to confirm.</Text>
              <TextField
                label="Password"
                value={password}
                onChangeText={setPassword}
                secureTextEntry
                autoCapitalize="none"
                autoComplete="password"
                textContentType="password"
              />
              {deleteError && (
                <Text variant="caption" tone="negative" accessibilityRole="alert">
                  {deleteError}
                </Text>
              )}
              <Button
                label="Permanently delete"
                variant="danger"
                onPress={confirmDelete}
                loading={isDeleting}
                disabled={password === ""}
              />
              <Button
                label="Cancel"
                variant="ghost"
                disabled={isDeleting}
                onPress={() => {
                  setDeleting(false);
                  setPassword("");
                  setDeleteError(null);
                }}
              />
            </>
          )}
        </Card>
      </ScrollView>
    </Screen>
  );
}

const useStyles = makeStyles(() =>
  StyleSheet.create({
    content: { paddingBottom: space.xxl },
    signOut: { paddingHorizontal: space.lg, paddingVertical: space.md },
    bank: { flexDirection: "row", alignItems: "center", gap: space.sm },
    flex: { flex: 1 },
    pressed: { opacity: 0.6 },
  })
);
