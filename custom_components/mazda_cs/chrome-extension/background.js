/**
 * Mazda OAuth Helper - Background Service Worker
 *
 * This extension intercepts the msauth.com.mazdausa.mazdaiphone://auth redirect from Mazda's
 * Auth0 mobile OAuth flow and extracts the authorization code.
 *
 * If the state parameter is a JWT containing a flow_id, it automatically
 * redirects to Home Assistant's OAuth endpoint.
 */

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

// Listen for navigation events that would redirect to msauth.com.mazdausa.mazdaiphone://auth
chrome.webNavigation.onBeforeNavigate.addListener(async (details) => {
  const url = details.url;

  // Check if this is the msauth.com.mazdausa.mazdaiphone://auth redirect
  if (url.startsWith("msauth.com.mazdausa.mazdaiphone://auth")) {
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

// Also listen for errors when Chrome can't handle msauth.com.mazdausa.mazdaiphone://auth
chrome.webNavigation.onErrorOccurred.addListener(async (details) => {
  // Check if the error was for a msauth.com.mazdausa.mazdaiphone://auth URL
  if (details.url && details.url.startsWith("msauth.com.mazdausa.mazdaiphone://auth")) {
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
