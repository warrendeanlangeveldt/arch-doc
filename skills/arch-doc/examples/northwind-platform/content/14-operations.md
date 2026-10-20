# operations

The platform support team runs the platform, with the build team on call until the team is staffed in July 2027. The platform is not ready for operation yet: configuration records, the production access model and the handover are all outstanding.

## views

We do not draw an operational support view until the support roster is final (EXC-04). The RACI below carries the same content.

## readiness

REGISTER readiness-item

## support-model

| Role | Holder | Responsibility |
|---|---|---|
| Business owner | Head of Platform | Funding, priorities and the consumer relationship |
| Service owner | Head of Platform until a service owner is appointed | Service levels and the service review |
| Application owner | Platform product manager | Catalogue, onboarding and the portal |
| Technical owner | Platform engineering lead | Gateway, broker, workflow runtime, pipeline |
| Security owner | Security architect | Identity, secrets, audit and security events |

The service desk takes first contact and routes platform faults to the platform support group. The platform support group is the second tier and the build team the third. Support hours are 08:00 to 18:00 on working days, with the build team's interim on-call roster outside those hours until July 2027. Severity 1 response is 15 minutes at all times; severity 2 is one hour in support hours. A broker or gateway outage over 15 minutes is a major incident (PRC-02).

## raci

| Activity | Platform support | Build team | Consumer team | Security operations | Service management |
|---|---|---|---|---|---|
| Triage platform incidents | R | C | I | I | A |
| Major incidents | R | R | C | C | A |
| Problems | A | R | C | I | C |
| Change and release | A | R | I | C | C |
| Access requests | R | C | R | I | A |
| Runbooks | A | R | C | C | I |
| Configuration records | R | C | I | I | A |
| Monitoring and alerts | A | R | R | C | I |
| Security incidents | C | C | I | A | I |

## service-records

The platform needs a business application record for the Northwind Platform, an application service for each published interface, a technical service for each zone, and records for each managed service in production. The environment templates create the zone and service records; the application services are maintained by the platform support lead. The record classes for platform services do not exist yet, and the service management team's date is at risk (DEP-04).

## model-mapping

| Model object type | Configuration record it informs |
|---|---|
| Application Component (the platform) | Business application |
| Application Interface | Application service |
| Node (a zone) | Technical service |
| System Software | Configuration item for the managed service |

The model is the source for what exists by design; the configuration records are the source for what runs. A weekly reconciliation (PRC-07) reports where they differ, and the platform support lead resolves each difference.
