# summary

We ask the {p:forums.design_authority.name} to approve the Northwind Platform capability design so that we can build release 1. The platform gives internal teams shared integration and event services, so that each team stops building and running its own.

## scope

This design covers release 1 of the Northwind Platform: the API gateway, event broker, workflow runtime, secrets store, workload identity, telemetry pipeline, platform portal and environment templates, in {count:environment} environments. It stops at the published interfaces. What a consumer builds on them belongs to that consumer's own design. Section {sec:context/in-scope} itemises the scope.

## decision-sought

REGISTER decision-request

DRQ-02 is needed because the platform departs from the integration reference architecture, as section {sec:decisions/deviations} explains. DRQ-03 asks the steering group to accept that the first consumers go live before the support team is fully staffed.

## overview

Teams integrate point to point today: nightly files, direct database reads, queues each team runs for itself and custom adapters. Failures surface when users notice them, and every team holds its own credentials to other teams' systems. Section {sec:current-state/integration-landscape} sets this out.

The platform replaces those paths with shared services in every environment. Consumers publish APIs through the gateway, exchange events through the broker, run long processes on the workflow runtime and read secrets with their own workload identity. The platform relies on the {p:systems.identity.name}, the {p:systems.monitoring.name} and the {p:systems.itsm.name}. It depends on no other design.

The design is complete enough to build, and it is not yet ready to run. {count:risk where rating=high} risks are rated high ({ids:risk where rating=high}). The most serious is that consumers adopt the platform before support is staffed (RSK-02). The pre-production zone is three weeks late (ISS-01), which pushes failover and load testing into January, close to go-live. Configuration record classes for platform services are at risk (DEP-04), and without them no incident can be raised against the platform.
