import { useEffect, useState } from "react";
import { Image, StyleSheet, View } from "react-native";
import { brandDomain, brandLogoUri } from "@/lib/brandLogos";
import { makeStyles } from "@/theme/theme";
import { Initial } from "./ListRow";

/**
 * Logo for an allowlisted household subscription, else the first letter.
 * Fetches Google's public favicon at paint time; nothing is stored.
 */
export function MerchantMark({ name, size = 40 }: { name: string; size?: number }) {
  const styles = useStyles();
  const domain = brandDomain(name);
  const [failed, setFailed] = useState(false);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    setFailed(false);
    setReady(false);
  }, [name, domain]);

  if (!domain || failed) return <Initial name={name} size={size} />;
  return (
    <View style={{ width: size, height: size }}>
      {!ready && <Initial name={name} size={size} />}
      <Image
        source={{ uri: brandLogoUri(domain) }}
        accessibilityIgnoresInvertColors
        onLoad={() => setReady(true)}
        onError={() => setFailed(true)}
        style={[styles.logo, { width: size, height: size, borderRadius: size / 2, opacity: ready ? 1 : 0 }]}
      />
    </View>
  );
}

const useStyles = makeStyles((colors) =>
  StyleSheet.create({
    logo: { position: "absolute", top: 0, left: 0, backgroundColor: colors.logoBacking },
  })
);
