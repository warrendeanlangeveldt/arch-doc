# target

The target is one set of integration services, run once for every team, in every environment, behind published interfaces.

## views

VIEW platform-layered | Northwind Platform: layered view | solution-context

## description

REGISTER capability where state=target|both cols id,title,description,realised_by

Consumers reach the platform through four published interfaces: API publication, events, workflows and secrets. Each consumer workload has its own identity from the {p:systems.identity.name}, so no consumer holds a shared credential. The platform forwards each consumer's telemetry to the {p:systems.monitoring.name}, tagged so the consumer sees its own, and alerts become incidents in the {p:systems.itsm.name}.

What changes for consumers: they stop running queues and adapters, onboard through the portal, and accept at-least-once delivery. What changes for the platform team: it runs shared services for every consumer and answers for their availability.

## diagram

FIGURE platform-overview | Northwind Platform: consumers, platform services and the organisation services it relies on

Read the figure from the top. Consumer services use the platform services in the middle; the platform relies on the organisation services at the bottom.

## principles

| Principle | Source | What it means here |
|---|---|---|
| Publish interfaces, hide internals | Integration reference architecture | Consumers use the published interfaces only (ADR-02); we can change partitions, tiers or runtimes without breaking them |
| One identity per workload | Security standard | No shared keys or connection strings anywhere on the platform (NFR-09) |
| Producers own their events | Reference architecture, event addendum | The producing team owns each topic, its schema and who may subscribe |
| Same shape in every environment | Platform strategy | Every zone is built from the same templates, so a test result predicts production |

## operating-model

Consumer teams take on idempotent processing and their own dead-letter queues; the platform alerts them, and they replay after a fix. The platform team becomes a service team with an on-call roster, which it does not have the people to staff out of hours until July 2027 (CON-03, RSK-02). The service desk learns to recognise a platform fault and route it to the platform support group (PRC-05).
