// OAuth banks (Chase, Wells Fargo, ...) send the user off to the bank's own
// site, then back to PLAID_REDIRECT_URI (/oauth-return?oauth_state_id=...).
// Plaid requires resuming Link there with the *same* link token, so it's
// stashed before Link opens and reused on return.
export const LINK_TOKEN_KEY = "bankr.plaidLinkToken";
export const OAUTH_RETURN_PATH = "/oauth-return";

export function isOAuthReturn() {
  return (
    window.location.pathname === OAUTH_RETURN_PATH && new URLSearchParams(window.location.search).has("oauth_state_id")
  );
}

export function leaveOAuthReturn() {
  localStorage.removeItem(LINK_TOKEN_KEY);
  if (window.location.pathname === OAUTH_RETURN_PATH) window.history.replaceState(null, "", "/");
}
