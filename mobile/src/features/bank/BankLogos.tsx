import { createContext, Fragment, useContext, useMemo, type ReactNode } from "react";
import { Image, StyleSheet, View } from "react-native";
import { fetchLinkedBanks } from "@/lib/api";
import { useResource } from "@/lib/useResource";
import { radius } from "@/theme/tokens";
import { makeStyles } from "@/theme/theme";
import { Text } from "@/ui";

// Ported from web/src/lib/bankLogos.tsx and web/src/components/BankLogo.tsx.

/** Bank name -> base64 logo, for every connected bank that has one. */
const BankLogosContext = createContext<ReadonlyMap<string, string>>(new Map());

/** Loads the linked banks once for the signed-in app; reloads after a bank sync. */
export function BankLogosProvider({ syncVersion, children }: { syncVersion: number; children: ReactNode }) {
  const { data } = useResource(fetchLinkedBanks, [syncVersion]);
  const logos = useMemo(
    () => new Map((data ?? []).flatMap((b) => (b.institution_logo ? [[b.institution_name, b.institution_logo] as const] : []))),
    [data]
  );
  return <BankLogosContext.Provider value={logos}>{children}</BankLogosContext.Provider>;
}

export function useBankLogos() {
  return useContext(BankLogosContext);
}

const logoUri = (logo: string) => `data:image/png;base64,${logo}`;

/** A bank's logo, or its first letter until one is available. */
export function BankLogo({ name, size = 32 }: { name: string; size?: number }) {
  const styles = useStyles();
  const logo = useBankLogos().get(name);
  if (logo) return <Image source={{ uri: logoUri(logo) }} style={[styles.logo, { width: size, height: size }]} />;
  return (
    <View style={[styles.fallback, { width: size, height: size }]}>
      <Text variant="label" tone="soft">
        {name.charAt(0).toUpperCase()}
      </Text>
    </View>
  );
}

/** Plain text in which every mention of a connected bank gets its small logo. Render inside a Text. */
export function BankText({ text }: { text: string }) {
  const styles = useStyles();
  const logos = useBankLogos();
  const pattern = useMemo(() => {
    const names = [...logos.keys()].sort((a, b) => b.length - a.length);
    if (names.length === 0) return null;
    const escaped = names.map((n) => n.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
    return new RegExp(`(${escaped.join("|")})`, "gi");
  }, [logos]);
  if (!pattern) return <>{text}</>;

  const byLowerName = new Map([...logos].map(([name, logo]) => [name.toLowerCase(), logo]));
  return (
    <>
      {text.split(pattern).map((part, i) => {
        const logo = i % 2 === 1 ? byLowerName.get(part.toLowerCase()) : undefined;
        return (
          <Fragment key={i}>
            {logo && <Image source={{ uri: logoUri(logo) }} style={styles.inline} />}
            {logo ? ` ${part}` : part}
          </Fragment>
        );
      })}
    </>
  );
}

const useStyles = makeStyles((colors) =>
  StyleSheet.create({
    logo: { borderRadius: radius.sm, backgroundColor: colors.logoBacking },
    fallback: { borderRadius: radius.sm, backgroundColor: colors.raised, alignItems: "center", justifyContent: "center" },
    inline: { width: 16, height: 16, borderRadius: 3, backgroundColor: colors.logoBacking },
  })
);
