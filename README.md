
# Introduction
This is a fork of the Mazda Connected Services integration originally written by bdr99 that has been packaged into a HACS compatible custom integration. The original code was part of the Home Assistant core integrations prior to a DMCA takedown notice issue by Mazda Motor Corporation.  It should restore all functionality previously available in the core integration.

# Mazda API v2 — MJO / 日本 / Australia Region
* Mazda has moved NA, EU, and CA, to v2 of their API with a new authentication method. However the Australian region is currently still using the v1 API. Android app changes indicate the switch is coming (has v2 information coded for AU), but Mazda is staggering release. EU was December, and NA/CA was February. The intgration should be ready for you as soon as Mazda switches your region.
* **[PLEASE STAY ON 1.8.5](https://github.com/fano0001/home-assistant-mazda/releases/tag/v1.8.5)** for now. Use the manual installation instructions below or manually select v1.8.5 in HACS under the 'mazda_cs' HACS page -> 3 dots top right-> Download/Redownload -> 'Need Another Vesion'.
* マツダは、北米（NA）、欧州（EU）、およびカナダ（CA）の各地域について、新しい認証方式を採用したAPIのバージョン2（v2）への移行を完了しました。しかしながら、オーストラリア地域については、現時点では依然としてv1 APIが使用されています。モバイルアプリの更新内容からは、まもなく移行が実施される兆候が見受けられます（アプリのコード内にオーストラリア向けのv2関連情報がすでに組み込まれています）が、マツダは各地域へのリリースを段階的に進めているようです。欧州地域への適用は12月に、北米・カナダ地域への適用は2月にそれぞれ行われました。マツダ側で貴殿の地域への切り替えが完了し次第、本連携機能も直ちにご利用いただけるようになる見込みです。（Google 翻訳）
* **[当面の間は 1.8.5 に留まってください](https://github.com/fano0001/home-assistant-mazda/releases/tag/v1.8.5)** 以下の手動インストール手順を使用するか、HACS の「mazda_cs」ページから手動で v1.8.5 を選択してください。右上の 3 つのドット→ダウンロード / 再ダウンロード→別のバージョンが必要。（Google 翻訳）

# Installation

## With HACS

1. Add this repository as a custom repository in HACS.
2. Download the integration.
3. Restart Home Assistant

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=fano0001&repository=home-assistant-mazda&category=integration)

## Manual
Copy the `mazda_cs` directory, from `custom_components` in this repository,
and place it inside your Home Assistant Core installation's `custom_components` directory. Restart Home Assistant prior to moving on to the `Setup` section.

`Note`: If installing manually, in order to be alerted about new releases, you will need to subscribe to releases from this repository.

# Authentication

> [!IMPORTANT]
> A browser extension is required to successfully authenticate with Mazda. Do not skip this step!
> The chrome extension is tied to the folder location on your computer and may disappear if you move the folder.

Mazda Connected Services uses OAuth authentication which blocks automated logins. Authentication requires a browser-based OAuth flow using a browser extension to capture the mobile app redirect URL.

## Setup

   ### chrome-extension
   
   - Download the [latest chrome-extension.zip](https://github.com/fano0001/home-assistant-mazda/releases/latest/download/chrome-extension.zip) from releases (or use `./browser-extensions/chrome-extension/` from source)
   - Extract the zip file (or use source)
   - Open Google Chrome and navigate to `chrome://extensions/` or Edge `edge://extensions/`
   - Enable "Developer mode"
   - Click "Load unpacked" and select the extracted folder
   - Try to authenticate

   ### safari-extension

   > Requires Xcode and a free developer account

   - Download the [latest safari-extension.zip](https://github.com/fano0001/home-assistant-mazda/releases/latest/download/safari-extension.zip) from releases (or use `./browser-extensions/safari-extension/` from source)
   - Extract the zip file
   - Open the Xcode project
   - Go to project settings and set your free developer account as the 'Team' for both Targets (`com.mazda.oauth-helper` and `com.mazda.oauth-helper.extension`). Also ensure 'Signing Certificate' is set to 'Development'
   - Quit Safari if open and build the extension
   - Open Safari and enable the extension in Safari settings
   - Build the extension again
   - The app window should indicate the extension is 'On'.

# Push Notification Events

Push notification events allow the integration to receive real-time updates from Mazda — for example, confirmation that a remote lock or unlock command was completed — without waiting for the next scheduled poll.

## How it works

When enabled, the integration registers with the andoid app's notification service. Push notifications are then sent to your Home Assistant, such as:

- A remote command (lock, unlock, start engine, etc.) success and failure
- A door being opened or left unlocked
- Charging completing or starting

After push events arrive the integration triggers an immediate refresh.

Events are fired as Home Assistant events under `mazda_cs_push`, which can be used as an automation trigger.

## Configuration 

### Enable push notification events

> [!IMPORTANT]
> Push notification events are **disabled by default** and must be opted in to.

**During initial setup**, a toggle to enable appears on setup alongside the region selector. 

**After setup**, you can enable or disable it at any time via **Settings → Devices & Services → Mazda Connected Services → Three Dots → Reconfigure**. No re-login is required.

**"Push notification events" switch** has been added to each vehicle's device page to temporarily increase discovery for existing users. Toggling it will reload the integration.

---

### Notification settings

Which notifications you receive can be configured per vehicle under **Settings → Devices & Services → Mazda Connected Services → Options**. Each supported notification type has its own toggle.

The **Save settings** toggle at the bottom of that screen controls whether the servers persist vehicle status notification choices. If disabled off, the notification choices are reset by the server to on after 24 hours. Save settings toggle is on by default.

---

### Example Automations YAML

Example yaml for sending Home Assistant notifications can be found in the example folder [HERE]().

---

## Known Issues / limitations

* Enabling push notifications increases integration reload and removal times. It can take up to 90s for the integration to disappear on removal or reload. 
* Removal can fail to cleanup and re-adding can cause a multiple-devices detected email. The integration will reconnect.

### Asymmetric events between accounts

If two accounts are used (primary + secondary user):

- The **primary account** receives push notification events for actions triggered by the secondary account.
- The **secondary account does not** receive push notification events for actions triggered by the primary account.