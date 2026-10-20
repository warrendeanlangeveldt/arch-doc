# context

The platform sits between the consumer teams and the organisation's shared services. It inherits the organisation's cloud landing zone, network hub, {p:systems.identity.name} and {p:systems.monitoring.name}, and it adds the integration services none of those provide.

## in-scope

| Item | Description |
|---|---|
| API gateway | Publishes internal and partner APIs, authenticates callers and applies rate limits |
| Event broker | Topics and subscriptions with ordering per key, dead-letter and a seven-day replay window |
| Workflow runtime | Long-running workflows with timers, retries and compensation |
| Secrets store and workload identity | A vault per consumer per environment, read with the workload's own identity |
| Telemetry pipeline | Metrics, logs and traces tagged by consumer and forwarded to the {p:systems.monitoring.name} |
| Platform portal and environment templates | Self-service onboarding, the API and topic catalogue, and templated resources in each zone |
| Consumer engineers | Onboard, publish and subscribe through the portal and the published interfaces |
| Platform support | Runs the platform in production, with the build team on call until July 2027 |

## out-of-scope

| Item | Why it is excluded | Where it is dealt with |
|---|---|---|
| Consumer services and their data | Each team designs and owns its own services | The consumer's own design |
| Exactly-once delivery | We chose at-least-once delivery with idempotent consumers (ADR-03) | Section {sec:decisions/decisions} |
| Replacing the finance file exchange | The finance systems change in 2027 and will consume events then | Section {sec:lifecycle/retired} |
| Partner contracts for external APIs | A commercial matter for each consumer | The consumer's own design |

## parent-alignment

The parent is the organisation's integration reference architecture 2.0, approved in 2025. We implement its API publication, identity and observability patterns as written. We depart from its central service bus pattern: the platform offers an event broker and an API gateway instead, and each team owns its own topics and APIs. The departure from the parent architecture is recorded in {sec:decisions/deviations} and needs approval.

## view-register

| View | Viewpoint | Object types | Mandatory for approval | Shown in |
|---|---|---|---|---|
| {view:current-landscape} | Application Cooperation | Application components and collaborations | Yes | Section {sec:current-state/views} |
| {view:platform-layered} | Layered | Application components, interfaces and collaborations | Yes | Section {sec:target/views} |
| {view:platform-components} | Application Structure | Application components and interfaces | Yes | Section {sec:application/views} |
| {view:platform-cooperation} | Application Cooperation | Application components, interfaces and collaborations | Yes | Section {sec:integration/views} |
| {view:platform-data} | Data access matrix | Data objects and application components | Yes | Section {sec:data/views} |
| {view:platform-deployment} | Technology | Locations, nodes, system software and networks | Yes | Section {sec:infrastructure/views} |

The traceability, operational support, release scope and retirement impact views are not drawn. EXC-03, EXC-04 and EXC-05 record why.

## traceability

Each business requirement traces to the components that satisfy it, and each constraint to the design response it forces.

REGISTER business-requirement cols id,title,satisfied_by,status

REGISTER constraint cols id,title,response,status

BR-05 (cost show-back) has no acceptance measure yet. It is an open item for the platform product manager, not an omission.
