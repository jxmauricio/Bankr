/**
 * Household consumer subscriptions only. A merchant gets a logo iff its name
 * contains one of these brands; otherwise it stays a letter and never hits
 * the network.
 *
 * In: streaming, software/SaaS, Apple/Google/Microsoft/Amazon, a few national
 * papers, national telecom. Out: grocers, restaurants, rent, local gyms,
 * regional utilities, delivery apps, banks.
 *
 * Nothing is stored. MerchantMark loads Google's public favicon for the
 * domain at paint time; the OS HTTP cache reuses it.
 *
 * Longer names first so "amazon prime" wins over "amazon".
 */
const BRANDS: { id: string; domain: string; exact?: boolean }[] = [
  { id: "amazon prime", domain: "amazon.com" },
  { id: "prime video", domain: "primevideo.com" },
  { id: "youtube tv", domain: "tv.youtube.com" },
  { id: "youtube premium", domain: "youtube.com" },
  { id: "youtube music", domain: "music.youtube.com" },
  { id: "google one", domain: "one.google.com" },
  { id: "microsoft 365", domain: "microsoft.com" },
  { id: "office 365", domain: "microsoft.com" },
  { id: "apple music", domain: "music.apple.com" },
  { id: "apple tv", domain: "tv.apple.com" },
  { id: "apple one", domain: "apple.com" },
  { id: "hbo max", domain: "max.com" },
  { id: "disney plus", domain: "disneyplus.com" },
  { id: "disneyplus", domain: "disneyplus.com" },
  { id: "paramount plus", domain: "paramountplus.com" },
  { id: "new york times", domain: "nytimes.com" },
  { id: "ny times", domain: "nytimes.com" },
  { id: "wall street journal", domain: "wsj.com" },
  { id: "t mobile", domain: "t-mobile.com" },
  { id: "at and t", domain: "att.com" },
  { id: "youtube", domain: "youtube.com" },
  { id: "netflix", domain: "netflix.com" },
  { id: "spotify", domain: "spotify.com" },
  { id: "hulu", domain: "hulu.com" },
  { id: "disney", domain: "disneyplus.com" },
  { id: "peacock", domain: "peacocktv.com" },
  { id: "paramount", domain: "paramountplus.com" },
  { id: "espn", domain: "espn.com" },
  { id: "adobe", domain: "adobe.com" },
  { id: "cursor", domain: "cursor.com" },
  { id: "github", domain: "github.com" },
  { id: "openai", domain: "openai.com" },
  { id: "chatgpt", domain: "openai.com" },
  { id: "anthropic", domain: "anthropic.com" },
  { id: "patreon", domain: "patreon.com" },
  { id: "dropbox", domain: "dropbox.com" },
  { id: "slack", domain: "slack.com" },
  { id: "zoom", domain: "zoom.us" },
  { id: "notion", domain: "notion.so" },
  { id: "figma", domain: "figma.com" },
  { id: "icloud", domain: "icloud.com" },
  { id: "apple", domain: "apple.com" },
  { id: "microsoft", domain: "microsoft.com" },
  { id: "google", domain: "google.com" },
  { id: "amazon", domain: "amazon.com" },
  { id: "audible", domain: "audible.com" },
  { id: "nytimes", domain: "nytimes.com" },
  { id: "wsj", domain: "wsj.com" },
  { id: "verizon", domain: "verizon.com" },
  { id: "xfinity", domain: "xfinity.com" },
  { id: "comcast", domain: "xfinity.com" },
  { id: "spectrum", domain: "spectrum.com" },
  { id: "att", domain: "att.com" },
  { id: "tmobile", domain: "t-mobile.com" },
  { id: "hbo", domain: "max.com" },
  { id: "max", domain: "max.com", exact: true },
];

function folded(name: string): string {
  return name
    .toLowerCase()
    .replace(/&/g, " and ")
    .replace(/[^a-z0-9]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/** Domain for a known brand in this merchant name, or null to keep the letter. */
export function brandDomain(name: string): string | null {
  const hay = ` ${folded(name)} `;
  if (hay === "  ") return null;
  for (const brand of BRANDS) {
    if (brand.exact) {
      if (folded(name) === brand.id) return brand.domain;
      continue;
    }
    if (hay.includes(` ${brand.id} `)) return brand.domain;
  }
  return null;
}

export function brandLogoUri(domain: string): string {
  return `https://www.google.com/s2/favicons?domain=${encodeURIComponent(domain)}&sz=128`;
}
