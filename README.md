
# Introduction
This is a fork of the Mazda Connected Services integration originally written by bdr99 that has been packaged into a HACS compatible custom integration. The original code was part of the Home Assistant core integrations prior to a DMCA takedown notice issue by Mazda Motor Corporation.  It should restore all functionality previously available in the core integration.

# Mazda API v2 — Australia Region
* Mazda has moved NA, EU, and CA, to v2 of their API with a new authentication method. However the Australian region is currently still using the v1 API. Android app changes indicate the switch is coming (has v2 information coded for AU), but Mazda is staggering release. EU was December, and NA/CA was February. The intgration should be ready for you as soon as Mazda switches your region.
* **[PLEASE STAY ON 1.8.5](https://github.com/fano0001/home-assistant-mazda/releases/tag/v1.8.5)** for now. Use the manual installation instructions below or manually select v1.8.5 in HACS under the 'mazda_cs' HACS page -> 3 dots top right-> Download/Redownload -> 'Need Another Vesion'.

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
> All steps below must be performed in a Chromium based browser.
> This chrome extension is required to successfully authenticate with Mazda. Do not skip this step!
> This extension is tied to the file location on your computer and may disappear if you move the folder.

Mazda Connected Services uses OAuth with CAPTCHA protection which blocks automated logins. Authentication requires a browser-based OAuth flow using a Chrome extension to capture the android mobile app's redirect URL.

## Setup
   - Download the [latest chrome-extension.zip](https://github.com/fano0001/home-assistant-mazda/releases/latest/download/chrome-extension.zip) from releases (or use `./chrome-extension/` from source)
   - Extract the zip file (or use source)
   - Open Google Chrome and navigate to `chrome://extensions/` or Edge `edge://extensions/`
   - Enable "Developer mode"
   - Click "Load unpacked" and select the extracted folder
   - Try to authenticate


