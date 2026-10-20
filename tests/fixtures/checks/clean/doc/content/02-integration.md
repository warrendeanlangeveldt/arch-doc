# integration
We run {count:integration where state=target} integrations in the target state. {view:int-flows} shows them.

## views
VIEW int-flows | Tracking integration flows | integration-flows

## overview
REGISTER integration where state=target

## contracts
Every new interface is versioned in its path and returns structured errors. Each contract is an OpenAPI
version 3.1 document, and every interface uses TLS 1.2 or later. The design decisions are in
{sec:decisions/decisions}.

## failure-handling
| Integration | Failure | Detection | Recovery |
|---|---|---|---|
| INT-01 | Scan backlog | Queue depth alert | Replay from the queue |
| INT-02 | Carrier timeout | Error rate alert | Retry with back-off |
| INT-03 | Rejected notification | Bounce report | Resend once |
| INT-04 | Label service down | Health check | Hold labels until it recovers |

## acceptance
REGISTER acceptance-item where stage=integration
