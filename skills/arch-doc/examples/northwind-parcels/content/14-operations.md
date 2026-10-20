# operations

Parcels Tracking Support will run the service, with the build team in hypercare for four weeks. Nothing about that team exists yet: no service owner, no assignment group and no roster. Operational readiness is the weakest part of the design.

## views

We do not draw an operational support view until the assignment groups exist (EXC-04). The RACI below carries the same content.

## readiness

REGISTER readiness-item

## support-model

| Role | Holder | Responsibility |
|---|---|---|
| Business owner | Head of Parcels | Outcomes, funding and the customer experience |
| Service owner | Not appointed; the Head of Parcels names one | Service levels, incidents and the service review |
| Application owner | Product owner, tracking | Backlog, releases and notification content |
| Technical owner | Integration lead | Components, integrations and runbooks |
| Platform services | Northwind Platform support | The platform interfaces we use ({dep:NP:operations/support-model}) |

The service desk takes first contact from agents and depots and routes to Parcels Tracking Support. Parcels Tracking Support is the second tier in business hours, 07:00 to 19:00 every day, because depots work weekends. Outside those hours a priority 1 pages the on-call engineer from the parcels digital team. The service levels are 99.9% availability for lookups and scan-to-visible within 60 seconds for 95% of scans. A tracking outage is a major incident after 15 minutes in business hours or 30 minutes outside them (PRC-02). Platform faults go to the platform's support group.

## raci

| Activity | Parcels Tracking Support | Parcels digital team | Depot operations | Platform support | Service desk |
|---|---|---|---|---|---|
| Triage incidents | R | C | I | C | A |
| Major incidents | R | R | C | C | A |
| Problems | A | R | C | C | I |
| Change and release | C | R | I | I | A |
| Access requests | R | I | A | I | C |
| Runbooks | A | R | C | C | I |
| Configuration items | R | C | I | I | A |
| Monitoring and alerts | A | R | I | C | I |
| Security incidents | C | R | I | C | I |
| Stalled parcels | I | I | A | I | I |

Security incidents are accountable to security operations, which is outside the table's columns; the parcels digital team responds for the application.

## service-records

Following CSDM, the service needs a business application, Parcel Tracking Solution; an application service, Parcel Tracking (production), with its offering for customers and one for agents; and the technical services of the platform zones, which the platform already holds. Service Mapping discovers the containers and the database under the application service; the application service, its offerings and their relationships to the platform's technical services are maintained by hand by the service owner. Assignment group Parcels Tracking Support takes incidents; the change group is Parcels Digital. None of these records exists yet (DEP-04).

## model-mapping

| Model object type | CSDM interpretation |
|---|---|
| Application Component (the solution) | Business application |
| Application Component (a component) | Application service CIs discovered by Service Mapping |
| Application Interface (platform) | Technical service, held by the platform |
| Node | Technical service for the platform zone |
| System Software | CI class for the container runtime or database |

The model is the design; the CMDB is what runs. The service owner compares them each quarter and either fixes the CMDB or raises a change to the design.
