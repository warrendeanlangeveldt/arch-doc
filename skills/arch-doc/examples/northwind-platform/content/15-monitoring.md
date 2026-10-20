# monitoring

We monitor the platform's availability, latency, capacity, errors, security and cost, and route each alert either to the platform on-call engineer or to the consumer team that owns the failing subscription.

## views

The operational support view is not drawn (EXC-04). {view:platform-cooperation} shows the path from the telemetry pipeline to the monitoring platform and the {p:systems.itsm.name}.

## coverage

REGISTER alert

ALT-04, ALT-05 and ALT-08 have no runbook. Each is a capacity or cost signal that the platform engineering lead reviews during support hours rather than an on-call action.

## correlation

Each alert carries the consumer tag and the zone. Alerts for the same service and zone within 10 minutes group into one incident. A broker outage raises one incident against the broker, and the dead-letter alerts it causes for each consumer are suppressed until the broker recovers.

## event-mapping

| Event source | Event | Configuration record | Correlation rule | Group alerted |
|---|---|---|---|---|
| Synthetic probes | Broker or gateway unavailable | Application service for the interface | Group by service and zone, 10 minutes | Platform support |
| Broker metrics | Dead-letter depth | The consumer's own application service | Group by subscription | Owning consumer team |
| Secrets store audit | Unexpected secret read | Technical service for the zone | None; each event is an incident | Security operations |
| Workflow runtime | Backlog | Application service for the workflow interface | Group by zone | Platform support |

Events that bind to no record are a gap, and they will happen until the record classes exist (DEP-04).

## acceptance

REGISTER acceptance-item where stage=monitoring
