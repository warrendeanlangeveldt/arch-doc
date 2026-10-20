# data

The platform carries consumers' data and holds its own. Consumer payloads belong to the producing team; the platform keeps them for seven days and never reads them. The platform's own data is metadata, secrets, audit records and telemetry.

## views

VIEW platform-data | Northwind Platform: data access | crud

## scope

REGISTER data-object

## flows

REGISTER data-flow

Payloads never reach telemetry. The broker forwards envelopes only (DF-02), so a consumer's confidential data does not land in the {p:systems.monitoring.name}.

## classification

| Data | Classification | Personal data | Privacy impact | Control |
|---|---|---|---|---|
| Event payload | Confidential, set by the producer | Possible; the producer declares it in the catalogue | Owned by the producer's privacy assessment | Encryption (CTL-05); topic access by approval (CTL-02) |
| Secret | Restricted | No | None | Vault per consumer, workload identity only (CTL-01, CTL-06) |
| Audit record | Confidential | Engineer identities | Low; used for audit only | Write-once store (CTL-10) |
| Envelope, catalogue, registration, telemetry | Internal | Contact names in registrations | Low | Access through the portal and the monitoring platform's own roles |

Producers must declare personal data in the catalogue before a topic goes live. We cannot check what a payload contains, and we say so to every producer at onboarding.

## retention

Retention follows the data object register. Events last seven days on the broker and are then deleted; nothing is archived. Workflow state is deleted 30 days after the workflow completes. Audit records stay online for one year and archived for six more, which falls short of the logging standard's two years online (EXC-02). Telemetry retention is set by the {p:systems.monitoring.name} and is still open (DAT-08). The security architect is accountable for audit records; the platform engineering lead for the rest.

## quality

| Rule | Check | Owner | Passing |
|---|---|---|---|
| Every event carries a complete envelope | Broker rejects publishes with missing envelope fields | Platform architect | No event without type, key, producer, time and schema version |
| Every topic has an owner and a schema | Portal will not create a topic without both | Platform product manager | Catalogue report shows no topic without an owner |
| Registrations match what exists | Weekly reconciliation of registrations against zone resources | Platform support lead | No orphaned vault, topic or route |
