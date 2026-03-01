
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

# Notifications
When a button is pressed, the integration starts a background process that polls the inbox in MyMazda 1-3 times (7s 12s 18s). As soon as a success or failure is detected, an event is fired in Home Assistant. This event can then be detected like any other and notifications can be sent through an automation. See examples below. 
* **Timing:** is specifically related to the intervals of typically responses for success/failure/rejection over 100 alerts. 
  * I may tweak the timing a second or two here and there, but I will keep this limitation, as both a sensible limitation and in an effort to reduce API calls to Mazda. Buttons presses send an event notification capturing the details.
  * In a further effort to reduce calls to Mazda, the integration will send null button presses until this check is complete (Mazda rejects them with a busy notification anyways).
## Every Event Example
```
alias: MyMazda Notify
description: ""
triggers:
  - event_type: mazda_cs_remote_service_result
    trigger: event
actions:
  - data:
      title: >-
        Mazda {{ action_labels.get(trigger.event.data.action,
        trigger.event.data.action) }} {{ 'Succeeded' if
        trigger.event.data.success else 'Failed' }}
      message: >-
        {% set label = action_labels.get(trigger.event.data.action,
        trigger.event.data.action) %} {% if trigger.event.data.success %}
          {{ label }} completed successfully.
        {% else %}
          {{ label }} failed: {{ trigger.event.data.details }}
        {% endif %}
    action: persistent_notification.create
variables:
  action_labels:
    doorLock: Door Lock
    doorUnlock: Door Unlock
    start_engine: Engine Start
    stop_engine: Engine Stop
    turn_on_hazard_lights: Hazard Lights On
    turn_off_hazard_lights: Hazard Lights Off
    flash_lights: Flash Lights
    hvacOn: Climate On
    hvacOff: Climate Off
    chargeStart: Charge Start
    chargeStop: Charge Stop
```
## Single Event
```
alias: DoorUnlock
description: ""
triggers:
  - event_type: mazda_cs_remote_service_result
    event_data:
      action: doorLock
      success: true
    trigger: event
actions:
  - data:
      message: "Door lock: {{ trigger.event.data.details }}"
    action: notify.mobile_phone #replace
mode: single

```
