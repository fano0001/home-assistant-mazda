/**
 * Mazda OAuth Helper - Background Service Worker
 *
 * Flow:
 *  1. User starts Mazda OAuth from Home Assistant.
 *  2. Chrome navigates to the Azure AD B2C authorize URL (*.id.mazda.com).
 *     We capture client_id, scope, redirect_uri, and token_url from that URL,
 *     indexed by the OAuth state parameter.
 *  3. After login, Azure B2C redirects to msauth://com.interrait.mymazda/...
 *     Chrome cannot handle this scheme, triggering onBeforeNavigate / onErrorOccurred.
 *  4. We extract the authorization code and state.
 *  5. For Home Assistant flows (state is a JWT containing flow_id):
 *     a. We perform the token exchange HERE in the browser via fetch().
 *        This bypasses Azure Front Door WAF, which blocks Python's TLS fingerprint
 *        (JA3) but allows browser requests.
 *     b. We base64url-encode the token JSON and prefix it with "MZDPRE_".
 *     c. We redirect to my.home-assistant.io/redirect/oauth with this as "code".
 *     d. HA's async_resolve_external_data detects the MZDPRE_ prefix and uses
 *        the token directly, skipping the blocked server-side exchange.
 *  6. For non-HA flows: show the capture page as before.
 */

const MAZDA_REDIRECT_PREFIXES = [
  "msauth.com.mazdausa.mazdaiphone://auth",
  "msauth://com.interrait.mymazda",
];

const MAZDA_AUTH_HOST_RE = /^https:\/\/[a-z]+\.id\.mazda\.com\//;

const MSAL_HEADERS = {
  "x-client-SKU": "MSAL.Android",
  "x-client-Ver": "5.4.0",
  "x-client-OS": "34",
  "x-client-DM": "Pixel 9",
  "x-client-CPU": "arm64-v8a",
  "x-app-name": "MyMazda",
  "x-app-ver": "9.0.8",
  Accept: "application/json",
};

// Keyed by OAuth state string → { client_id, scope, redirect_uri, token_url }
const pendingFlows = {};

function isMazdaRedirect(url) {
  return MAZDA_REDIRECT_PREFIXES.some((prefix) => url.startsWith(prefix));
}

function isHomeAssistantFlow(state) {
  if (!state) return false;
  try {
    const parts = state.split(".");
    if (parts.length !== 3) return false;
    const payload = JSON.parse(atob(parts[1]));
    return payload && typeof payload.flow_id === "string";
  } catch (e) {
    return false;
  }
}

// Step 2: capture auth URL params when Chrome navigates to Mazda B2C authorize page.
chrome.webNavigation.onBeforeNavigate.addListener((details) => {
  const url = details.url;

  if (MAZDA_AUTH_HOST_RE.test(url) && url.includes("/oauth2/v2.0/authorize")) {
    try {
      const urlObj = new URL(url);
      const state = urlObj.searchParams.get("state");
      const client_id = urlObj.searchParams.get("client_id");
      const scope = urlObj.searchParams.get("scope");
      const redirect_uri = urlObj.searchParams.get("redirect_uri");
      // Derive token URL: same path prefix, replace "authorize" → "token"
      const token_url =
        url.substring(0, url.indexOf("/oauth2/v2.0/authorize")) +
        "/oauth2/v2.0/token";

      if (state && client_id) {
        pendingFlows[state] = { client_id, scope, redirect_uri, token_url };
      }
    } catch (e) {
      console.error("Mazda OAuth Helper: failed to parse auth URL", e);
    }
    return; // don't interfere with the auth page navigation
  }

  if (isMazdaRedirect(url)) {
    handleMazdaRedirect(details.tabId, url);
  }
});

// Also catch cases where Chrome errors on the msauth:// scheme.
chrome.webNavigation.onErrorOccurred.addListener((details) => {
  if (details.url && isMazdaRedirect(details.url)) {
    handleMazdaRedirect(details.tabId, details.url);
  }
});

async function handleMazdaRedirect(tabId, url) {
  let urlObj;
  try {
    urlObj = new URL(url);
  } catch (e) {
    return;
  }

  const code = urlObj.searchParams.get("code");
  const state = urlObj.searchParams.get("state");

  if (code && isHomeAssistantFlow(state)) {
    const flow = pendingFlows[state];
    delete pendingFlows[state];

    if (flow) {
      try {
        const preToken = await exchangeToken(flow, code);
        const haUrl = new URL("https://my.home-assistant.io/redirect/oauth");
        haUrl.searchParams.set("code", preToken);
        haUrl.searchParams.set("state", state);
        chrome.tabs.update(tabId, { url: haUrl.toString() });
        return;
      } catch (err) {
        console.error("Mazda OAuth Helper: browser token exchange failed", err);
        // Fall through to plain code redirect so user sees the error in HA logs
      }
    }

    // No stored flow params or exchange failed — send the raw code and let HA try
    const haUrl = new URL("https://my.home-assistant.io/redirect/oauth");
    haUrl.searchParams.set("code", code);
    haUrl.searchParams.set("state", state);
    chrome.tabs.update(tabId, { url: haUrl.toString() });
    return;
  }

  // Non-HA flow: show capture page
  const captureUrl = new URL(chrome.runtime.getURL("capture.html"));
  captureUrl.searchParams.set("code", code || "");
  captureUrl.searchParams.set("state", state || "");
  captureUrl.searchParams.set(
    "error",
    urlObj.searchParams.get("error") || "",
  );
  captureUrl.searchParams.set(
    "error_description",
    urlObj.searchParams.get("error_description") || "",
  );

  if (code) {
    chrome.action.setBadgeText({ text: "✓" });
    chrome.action.setBadgeBackgroundColor({ color: "#4CAF50" });
  }

  chrome.tabs.update(tabId, { url: captureUrl.toString() });
}

/**
 * Exchange authorization code for tokens via browser fetch().
 * Returns a "MZDPRE_<base64url>" string that HA's async_resolve_external_data
 * recognises as a pre-exchanged token.
 */
async function exchangeToken(flow, code) {
  const body = new URLSearchParams({
    client_id: flow.client_id,
    grant_type: "authorization_code",
    code: code,
    redirect_uri:
      flow.redirect_uri ||
      "msauth://com.interrait.mymazda/%2FnKMu1%2BlCjy5%2Be7OF9vfp4eFBks%3D",
    scope: flow.scope || "",
  });

  const response = await fetch(flow.token_url, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
      ...MSAL_HEADERS,
    },
    body: body.toString(),
  });

  const contentType = response.headers.get("Content-Type") || "";
  if (!response.ok || contentType.includes("html")) {
    const text = await response.text();
    throw new Error(`Token endpoint returned ${response.status}: ${text.slice(0, 200)}`);
  }

  const token = await response.json();
  if (token.error) {
    throw new Error(token.error_description || token.error);
  }

  // Encode as base64url (URL-safe, no padding) with MZDPRE_ sentinel
  const encoded = btoa(JSON.stringify(token))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");

  return "MZDPRE_" + encoded;
}
