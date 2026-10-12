import { Fragment, useMemo, type ReactNode } from "react";
import { useBankLogos } from "../lib/bankLogos";

const logoSrc = (logo: string) => `data:image/png;base64,${logo}`;

/** A bank's logo (Plaid's base64 PNG), or its first letter until one is available. */
export function BankLogo({ name, logo }: { name: string; logo: string | null }) {
  if (logo) {
    return <img src={logoSrc(logo)} alt="" className="size-9 shrink-0 rounded-lg bg-white object-contain" />;
  }
  return (
    <span
      aria-hidden="true"
      className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-raised text-sm font-medium text-ink-soft"
    >
      {name.charAt(0).toUpperCase()}
    </span>
  );
}

function InlineLogo({ logo }: { logo: string }) {
  return <img src={logoSrc(logo)} alt="" className="mr-1 inline-block size-4 rounded-[3px] bg-white object-contain align-[-3px]" />;
}

/** `children` (default: the bank's name) with the bank's small logo in front,
 * when it has one. */
export function BankName({ bank, children }: { bank: string; children?: ReactNode }) {
  const logo = useBankLogos().get(bank);
  return (
    <>
      {logo && <InlineLogo logo={logo} />}
      {children ?? bank}
    </>
  );
}

/** Plain text in which every mention of a connected bank gets its small logo. */
export function BankText({ text }: { text: string }) {
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
            {logo && <InlineLogo logo={logo} />}
            {part}
          </Fragment>
        );
      })}
    </>
  );
}
