import { createContext, useContext, useMemo, type ReactNode } from "react";
import type { LinkedBank } from "./api";

/** Bank name -> base64 logo, for every connected bank that has one. */
const BankLogosContext = createContext<ReadonlyMap<string, string>>(new Map());

export function BankLogosProvider({ banks, children }: { banks: LinkedBank[]; children: ReactNode }) {
  const logos = useMemo(
    () => new Map(banks.flatMap((b) => (b.institution_logo ? [[b.institution_name, b.institution_logo] as const] : []))),
    [banks],
  );
  return <BankLogosContext.Provider value={logos}>{children}</BankLogosContext.Provider>;
}

export function useBankLogos() {
  return useContext(BankLogosContext);
}
