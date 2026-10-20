# transition

We go live over two weeks in January 2027: production first, then one pilot consumer, then every registered consumer. The way back is open until the platform opens to all consumers.

## views

We do not draw a release scope view (EXC-05). Release 1 is one plateau; the cutover register says what moves and when.

## cutover

REGISTER cutover-step

## rollback

| Failure | Trigger | Rollback action | Owner | Longest it may take |
|---|---|---|---|---|
| Platform services fail their smoke test | Any smoke test fails after CUT-03 | Remove the production deployment; no consumer is affected yet | Platform engineering lead | 2 hours |
| Monitoring or incident forwarding does not work | Test alert does not reach the on-call engineer | Hold the pilot; fix forwarding before CUT-05 | Platform engineering lead | 1 day |
| Pilot consumer cannot run on the platform | Pilot misses its latency target or loses events | Pilot returns to its team-run queue, kept running in parallel until CUT-06 | Platform product manager | 4 hours |

After CUT-06 there is no rollback to team-run queues; problems are fixed forward.

## hypercare

Hypercare runs from 25 January to 19 February 2027. The build team staffs it in support hours and holds the on-call roster outside them. Issues reach it through the platform support group, and it reports daily to the Head of Platform for the first two weeks and weekly after that.

## hypercare-exit

REGISTER acceptance-item where stage=hypercare-exit

## handover

REGISTER readiness-item where area=handover
