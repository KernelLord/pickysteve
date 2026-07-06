---
id: incident-response
name: Production Incident Response
description: Run a live production incident — triage, mitigate, communicate, and write the blameless postmortem.
tags: [incident, oncall, production, outage, sre, postmortem, mitigation, runbook, reliability]
---
# Production Incident Response

Use during or right after a production incident — an outage, data issue, or severe
regression in production. Typical triggers: the site is **down**, the **checkout** or
**payment** page is **throwing 500s** to customers, error rates just spiked, you've
been **paged**, or a deploy broke prod and you need to handle it live.

## Capabilities
- Triage and severity: declare severity, assign incident commander, stop the bleeding.
- Mitigation-first: roll back or feature-flag off before root-causing.
- Communication cadence: status updates to stakeholders on a clock.
- Blameless postmortem: timeline, contributing factors, and concrete action items.
- Distinguishes mitigation (now) from remediation (later).

## Notes
Live-incident operations and the postmortem. Root-causing a slow system without an
outage is performance-profiler's job.
