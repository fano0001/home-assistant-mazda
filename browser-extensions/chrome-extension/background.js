/**
 * Mazda OAuth Helper - Background Service Worker
 *
 * This extension intercepts Mazda mobile OAuth redirects and extracts the
 * authorization code. Two redirect URI schemes are handled:
 *   - msauth.com.mazdausa.mazdaiphone://auth  (iOS / MazdaUSA app)
 *   - msauth://com.interrait.mymazda           (Android / MyMazda app)
 *
 * If the state parameter is a JWT containing a flow_id, it automatically
 * redirects to Home Assistant's OAuth endpoint.
 */

const MAZDA_REDIRECT_PREFIXES = [
  "msauth.com.mazdausa.mazdaiphone://auth",
  "msauth://com.interrait.mymazda",
];

function isMazdaRedirect(url) {
  return MAZDA_REDIRECT_PREFIXES.some((prefix) => url.startsWith(prefix));
}

// Check if state is a JWT with flow_id (for Home Assistant)
function isHomeAssistantFlow(state) {
  if (!state) return false;
  try {
    // JWT has 3 parts separated by dots
    const parts = state.split(".");
    if (parts.length !== 3) return false;

    // Decode the payload (middle part)
    const payload = JSON.parse(atob(parts[1]));
    return payload && typeof payload.flow_id === "string";
  } catch (e) {
    return false;
  }
}

// Listen for navigation events that would redirect to a Mazda OAuth URI
chrome.webNavigation.onBeforeNavigate.addListener(async (details) => {
  const url = details.url;

  if (isMazdaRedirect(url)) {
    // Parse the URL to extract the authorization code
    const urlObj = new URL(url);
    const code = urlObj.searchParams.get("code");
    const state = urlObj.searchParams.get("state");

    // Check if this is a Home Assistant flow
    if (code && isHomeAssistantFlow(state)) {
      // Redirect to Home Assistant OAuth endpoint
      const haUrl = new URL("https://my.home-assistant.io/redirect/oauth");
      haUrl.searchParams.set("code", code);
      haUrl.searchParams.set("state", state);

      chrome.tabs.update(details.tabId, { url: haUrl.toString() });
      return;
    }

    // Otherwise, show capture page
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

    chrome.tabs.update(details.tabId, { url: captureUrl.toString() });
  }
});

// Also listen for errors when Chrome can't handle a Mazda OAuth URI
chrome.webNavigation.onErrorOccurred.addListener(async (details) => {
  if (details.url && isMazdaRedirect(details.url)) {
    const urlObj = new URL(details.url);
    const code = urlObj.searchParams.get("code");
    const state = urlObj.searchParams.get("state");

    // Check if this is a Home Assistant flow
    if (code && isHomeAssistantFlow(state)) {
      // Redirect to Home Assistant OAuth endpoint
      const haUrl = new URL("https://my.home-assistant.io/redirect/oauth");
      haUrl.searchParams.set("code", code);
      haUrl.searchParams.set("state", state);

      chrome.tabs.update(details.tabId, { url: haUrl.toString() });
      return;
    }

    // Otherwise, show capture page
    const captureUrl = new URL(chrome.runtime.getURL("capture.html"));
    captureUrl.searchParams.set("code", code || "");

    if (code) {
      chrome.action.setBadgeText({ text: "✓" });
      chrome.action.setBadgeBackgroundColor({ color: "#4CAF50" });
    }

    chrome.tabs.update(details.tabId, { url: captureUrl.toString() });
  }
});
