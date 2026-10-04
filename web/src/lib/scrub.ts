// Pure helpers that keep URLs' query strings and fragments out of error
// reports. Kept free of imports so they can be exercised without a browser.
//
// Why it matters here: Bankr's API calls carry search terms in the query
// (merchant, category), invite links carry a code, and Plaid's OAuth return
// carries an oauth_state_id -- none of that belongs in a third-party log.

export function stripQuery(url: string): string {
  const cut = url.search(/[?#]/);
  return cut === -1 ? url : url.slice(0, cut);
}

interface ReportLike {
  request?: { url?: string; query_string?: unknown; cookies?: unknown; headers?: Record<string, unknown> };
  breadcrumbs?: { data?: Record<string, unknown> }[];
}

export function scrubReport<T extends ReportLike>(event: T): T {
  if (event.request) {
    if (event.request.url) event.request.url = stripQuery(event.request.url);
    delete event.request.query_string;
    delete event.request.cookies;
    if (event.request.headers) delete event.request.headers.Referer;
  }
  for (const crumb of event.breadcrumbs ?? []) {
    const data = crumb.data;
    if (!data) continue;
    for (const key of ["url", "from", "to"]) {
      if (typeof data[key] === "string") data[key] = stripQuery(data[key]);
    }
  }
  return event;
}
