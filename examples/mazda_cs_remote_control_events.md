## Notifications — Every Event Example

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

## Notifications — Single Event Example

```
alias: DoorLock
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
