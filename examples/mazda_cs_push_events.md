## Notifications — Every Event Example

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
