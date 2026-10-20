# context

Parcel tracking sits between the depots and carriers that know where a parcel is and the customers and agents who want to know. It runs on the Northwind Platform and inherits the platform's zones, identity, secrets and telemetry.

## in-scope

| Item | Description |
|---|---|
| Scan and manifest intake | Depot scans and manifests as events through the platform |
| Carrier intake | Webhooks from carriers A and C; polling of carrier B |
| Tracking service and store | One timeline per parcel, its derived status, kept for eighteen months |
| Tracking API | Public lookups by parcel number and postcode; internal lookups for agents |
| Customer notifications | Email and SMS on status change, by the customer's preference |
| Ops dashboard and exception workflows | Stalled parcels, missed scans and depot lag for operations staff |
| Monitoring and incidents | {p:systems.monitoring.name} monitors and {p:systems.itsm.name} incidents for the service |
| Customers, agents, depot staff and operations leads | The people who use it |

## out-of-scope

| Item | Why it is excluded | Where it is dealt with |
|---|---|---|
| The platform's own services | The platform is its own design | {dep:NP} |
| Changes to the handheld app beyond publishing scans | The depot team owns the app | Depot operations roadmap |
| Delivery time predictions | Needs a year of timelines first | A later release |
| Migrating legacy scan history | The old files would build wrong timelines (ADR-07) | Section {sec:decisions/decisions} |

## parent-alignment

The parent architectures are the Northwind Platform design ({dep:NP}) and the organisation's integration reference architecture 2.0. We use the platform only through its published interfaces, as its design requires. We follow the reference architecture except for carrier B, which we poll because it cannot push (EXC-01, section {sec:decisions/deviations}).

## view-register

| View | Viewpoint | Object types | Mandatory for approval | Shown in |
|---|---|---|---|---|
| {view:pts-current} | Application Usage | Business actors and application components | Yes | Section {sec:current-state/views} |
| {view:pts-layered} | Layered | Business actors, application components and platform interfaces | Yes | Section {sec:target/views} |
| {view:pts-components} | Application Structure | Application components | Yes | Section {sec:application/views} |
| {view:pts-integration} | Application Cooperation | Application components and interfaces | Yes | Section {sec:integration/views} |
| {view:pts-data} | Data access matrix | Data objects and application components | Yes | Section {sec:data/views} |
| {view:pts-deployment} | Technology | Locations, nodes, system software and networks | Yes | Section {sec:infrastructure/views} |

The traceability, operational support, release scope and retirement views are not drawn; EXC-03, EXC-04 and EXC-05 record why.

## traceability

REGISTER business-requirement cols id,title,satisfied_by,status

REGISTER constraint cols id,title,response,status

Every business requirement has a design response. None is verified yet; verification happens in pre-production and hypercare.
