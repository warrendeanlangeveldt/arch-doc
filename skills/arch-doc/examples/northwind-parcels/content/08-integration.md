# integration

Every integration runs over a published platform interface or a carrier's own API, and every one of them can fail without losing a scan.

## views

VIEW pts-integration | Parcel Tracking Solution: integrations | integration-flows

## overview

REGISTER integration where state=target

The messaging provider's interface is open until the contract is signed (INT-06, DEP-03).

## contracts

FIGURE scan-journey | A scan from the handheld to the customer's notification and lookup

| Interface | Operations | Payload | Authentication | Versioning | Errors |
|---|---|---|---|---|---|
| Scan route and topic parcels.scans | Publish a scan | Parcel number, depot or van, scan type, scan time with offset, handheld id | Handheld client credentials at the platform gateway | Schema version in the platform envelope | Handheld retries and buffers offline |
| Webhook route for carriers A and C | Receive a status | Carrier payload, signed with the carrier's secret | Signature check (CTL-07) | Carrier version header; one mapping per version | 2xx only after the update is stored; carriers retry for 24 hours |
| Carrier B tracking API | List status changes since a position | Carrier status records | Carrier-issued API key from the platform secret interface | Carrier B's published version | Back off on 429; resume from the last position |
| GET /parcels/{number}?postcode= | Public lookup | Status, last event, expected day | Website client credentials | Major version in the path | 404 for no match, including a wrong postcode |
| GET /internal/parcels/{number} | Agent lookup | Full timeline with carrier detail and contact | {p:systems.itsm.name} client credentials | Major version in the path | 404 for no match |

The platform's side of each interface, its envelope and its retry behaviour are defined in {dep:NP:integration/contracts}.

## failure-handling

| Integration | Failure that matters | Business impact | Detection | Recovery | Who acts |
|---|---|---|---|---|---|
| INT-01 Depot scans to the tracking service | Ingest stops | Tracking stops updating | ALT-01 | Scans wait on the platform for seven days; replay (RBK-01) | Parcels Tracking Support |
| INT-02 Carrier B status updates | Rate limit or outage | Carrier B parcels go stale | ALT-05 | Back off and resume (RBK-02) | Parcels Tracking Support |
| INT-03 Status changes to the customer notification service | Notification service fails | Customers are not told | ALT-04 | Dead-letter and replay (RBK-01) | Parcels Tracking Support |
| INT-04 Carrier A and C status webhooks | Receiver down or signatures failing | Carrier A and C parcels go stale | ALT-07 and webhook error rate | Carriers retry for 24 hours; rotate a secret (RBK-06) | Parcels Tracking Support |
| INT-05 Public tracking lookups | API errors or slow | Customers cannot track | ALT-02, ALT-03 | RBK-04 | Parcels Tracking Support |
| INT-06 Notification delivery | Provider outage | Customers are not told | ALT-06 | Retry for an hour, then record as failed (RBK-03) | Product owner |
| INT-07 Parcel manifests | Manifests late | Scans wait for an unknown parcel | Unmatched-scan count on the dashboard | Scans held 12 hours, then flagged | Depot operations manager |
| INT-08 Telemetry to Datadog | Export stops | We are blind to faults | Platform collector alarm | Collector buffers an hour | Platform on-call |
| INT-09 Datadog alerts to ServiceNow incidents | Incident creation fails | Faults reach nobody through the service desk | Datadog integration error | Datadog pages the on-call engineer | Service owner |
| INT-10 Customer service lookups | Internal route fails | Agents fall back to carrier portals | ALT-02 | RBK-04 | Parcels Tracking Support |
| INT-11 Staff sign-in to the ops dashboard | Identity provider down | Dashboard unavailable | Sign-in failures | None on our side; wait for the provider | Security architect |

## acceptance

REGISTER acceptance-item where stage=integration
