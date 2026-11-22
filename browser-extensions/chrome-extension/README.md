# Mazda OAuth Helper (legacy Chrome extension)

> [!NOTE]
> This extension is no longer actively maintained. Use [OAuth Assist for HA](../../README.md#oauth-assist-for-ha-chrome-and-firefox-extensions) instead, or the [manual sign-in](../../README.md#manual-authentication). Install steps for this extension are in [examples/legacy-extension.md](../../examples/legacy-extension.md).

Mazda's sign-in (Azure AD B2C) finishes by redirecting to a mobile-app URL scheme that a desktop browser cannot open:

- `msauth://com.interrait.mymazda/...` (MyMazda Android app)
- `msauth.com.mazdausa.mazdaiphone://auth...` (MazdaUSA iOS app)

This extension watches for that redirect and hands the authorization code to Home Assistant, so the integration's **Automated sign-in (browser extension)** option can complete.

## How it works

1. You sign in on Mazda's login page (`*.id.mazda.com`) from the Home Assistant config flow.
2. Mazda redirects to one of the `msauth` URLs above, with `code` and `state` in the query string. Chrome cannot open it.
3. `background.js` catches the navigation (`webNavigation.onBeforeNavigate`, with `onErrorOccurred` as a fallback).
4. If `state` is a Home Assistant flow (a JWT whose payload has a `flow_id`), the tab is sent to `https://my.home-assistant.io/redirect/oauth?code=…&state=…`, which returns you to your Home Assistant instance to finish setup.
5. Otherwise the tab shows `capture.html`, with the code masked to its last 4 characters and a button to copy it.

The toolbar popup has one action: **clear Mazda sign-in cookies** for the `na`/`eu`/`ap`/`au.id.mazda.com` login hosts. Use it if the Mazda login page does not load or keeps reusing an old session.

## Files

- `manifest.json`: Manifest V3 configuration. Permissions `webNavigation`, `tabs`, `cookies`; host access limited to the four Mazda login hosts.
- `background.js`: service worker that catches the redirect and routes it.
- `popup.html` / `popup.js`: toolbar popup (cookie clearing).
- `capture.html` / `capture.js`: fallback page showing the captured code.
- `icon*.svg`: icons.

## Security notes

- The extension does not store the code. It is passed in the URL of the Home Assistant redirect or the capture page, so it appears in browser history.
- The code is single-use, expires within minutes, and can only be redeemed by the Home Assistant instance that started the sign-in (PKCE).
