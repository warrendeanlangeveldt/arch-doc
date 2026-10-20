# integration

Consumers use the platform through its published interfaces, and the platform uses the organisation's identity, monitoring and service management services. Every interface fails safe: a failed publication leaves the last good route, and an undeliverable event waits in a dead-letter queue.

## views

VIEW platform-cooperation | Northwind Platform: application cooperation | integration-flows

## overview

REGISTER integration where state=target

The telemetry stream's protocol is still open (INT-02). The platform engineering lead decides it once the collector agents are chosen.

## contracts

| Interface | Operations | Payload | Authentication | Versioning | Errors |
|---|---|---|---|---|---|
| API publication interface | Publish, update or retire a route | Route definition and policy set | Pipeline workload identity | The route carries its API's major version in the path | Rejected publication keeps the previous route live |
| Event interface | Publish; subscribe; acknowledge; replay | The event in the platform envelope (DAT-01) | Workload identity, scoped per topic | Schema version in the envelope; backward-compatible changes only | Retry with backoff, then dead-letter |
| Workflow interface | Start; signal; query; cancel | Workflow input, keyed by the caller's idempotency key | Workload identity | Workflow definitions versioned per consumer | A repeated start with the same key returns the running instance |
| Secret interface | Read; list versions; receive rotation notice | Secret value to the owning workload only | Workload identity, scoped per vault | Each secret keeps its previous version for 30 days | Read denied is logged and alerted (ALT-06) |

The full field-level contracts sit in the interface guide that the platform product manager publishes before onboarding opens (RDY-06).

## failure-handling

FIGURE event-delivery | Event delivery, retry, dead-letter and replay

| Integration | Failure that matters | Business impact | Detection | Recovery | Who acts |
|---|---|---|---|---|---|
| INT-01 Identity federation for platform services | Identity provider unavailable | New sign-ins and token refreshes fail; running workloads keep working for up to an hour | Token failures in platform telemetry | Wait for the provider; no platform action restores it | Security architect |
| INT-02 Platform telemetry export | Export stops | Consumers and on-call lose sight of the platform | Collector buffer alarm in each zone | Collectors buffer for an hour and resend | Platform on-call |
| INT-04 Event publish and subscribe | A subscriber fails on an event | That consumer's processing stops for the affected key | Dead-letter depth (ALT-03) | Fix the subscriber, replay from dead-letter (RBK-01) | Owning consumer team |
| INT-04 Event publish and subscribe | Broker unavailable | Every producer and subscriber stops | Publish probe (ALT-01) | Fail over to the paired region (RBK-02) | Platform on-call |
| INT-03 API publication | Gateway unavailable | Internal and partner API calls fail | Health probe (ALT-02) | Restart or redeploy; certificate renewal (RBK-03) | Platform on-call |
| INT-05 Workflow start and callback | Callback endpoint unavailable | The consumer's workflow stalls at that step | Workflow backlog (ALT-07) | Callbacks retry for 24 hours; clear stuck instances (RBK-06) | Owning consumer team |
| INT-06 Secret retrieval | Rotation breaks a workload | That consumer cannot reach its dependencies after restart | Workload start failures in the consumer's telemetry | Roll back to the previous secret version | Owning consumer team |
| INT-07 Environment deployment | Deployment fails part way | The zone keeps the last good version; the release waits | Pipeline failure | Fix and rerun; nothing to roll back | Platform engineering lead |
| INT-08 Alerts to the service management platform | Incident creation fails | Alerts reach nobody through the service desk | Alerts queue in the monitoring platform | Monitoring platform pages the on-call engineer directly | Platform support lead |

## acceptance

REGISTER acceptance-item where stage=integration
