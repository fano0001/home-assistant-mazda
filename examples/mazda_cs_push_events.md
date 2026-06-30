## Notifications — Remote command and Vehicle Status

```
alias: Mazda Notify
description: ""
triggers:
  - event_type: mazda_cs_push
    trigger: event
actions:
  - choose:
      - conditions:
          - condition: template
            value_template: "{{ trigger.event.data.action_code == '001' }}"
        sequence:
          - data:
              title: >-
                Mazda — {{ trigger.event.data.title }} {{ 'Succeeded' if
                trigger.event.data.result_id.endswith('_01') else 'Failed' }}
              message: |-
                {% if trigger.event.data.result_id.endswith('_01') %}
                  {{ trigger.event.data.title }} completed successfully.
                {% else %}
                  {{ trigger.event.data.title }} failed: {{ trigger.event.data.body }}
                {% endif %}
              data:
                push:
                  interruption-level: time-sensitive
                ttl: 0
                priority: high
            action: persistent_notification.create
      - conditions:
          - condition: template
            value_template: "{{ trigger.event.data.action_code == '003' }}"
        sequence:
          - data:
              title: Mazda — {{ trigger.event.data.title }}
              message: >-
                {% set lines = trigger.event.data.body.replace('\r\n',
                '\n').split('\n') %} {% set alerts = lines
                  | reject('search', 'Tap Check Vehicle Status')
                  | reject('equalto', '')
                  | list %}
                {% for alert in alerts %}
                  - {{ alert }}
                {% endfor %}
              data:
                push:
                  interruption-level: time-sensitive
                ttl: 0
                priority: high
            action: persistent_notification.create
```

## Action Codes
```
# Action codes that trigger a refresh
        "001",   # INBOX_REMOTE — remote command result (lock/unlock/engine/A/C/lights)
        "003",   # INBOX_VEHICLE_STATUS
        "004",   # INBOX_SECURITY — Security alerts
        "019",   # INBOX_REMOTE_AC_EXTENSION
        "021",   # INBOX_EV_REMOTE
        "022",   # INBOX_REAL_TIME_VEHICLE_STATUS
        "023",   # INBOX_EV_VEHICLE_STATUS
        "026",   # INBOX_LOW_BATTERY - Low 12V battery
        "027",   # INBOX_EV_LOW_BATTERY
        "032",   # INBOX_GEOFENCE_ALERT
        "D002",  # CDT_INBOX_CP_CHARGE_COMPLETED
# Action codes documented but not requiring a refresh:
        # "009",   # INBOX_BCALL_HIGH - B-Call high priority
        # "014",   # INBOX_BCALL_LOW - B-Call low priority
        # "017",   # INBOX_TAKEOVER_FAILED - Takeover failed
        # "024",   # INBOX_ECONNECT_EVENT - eConnect event
        # "029",   # INBOX_EV_BATTERY_ADVICE - EV battery advice
        # "030",   # INBOX_EV_BATTERY_PRAISE - EV battery praise
        # "031",   # INBOX_GEOFENCE_SETTING - Geofence settings
        # "033",   # INBOX_SVT_SETTING - SVT (Stolen Vehicle Tracking) settings
        # "034",   # INBOX_SVT_ALERT
```
