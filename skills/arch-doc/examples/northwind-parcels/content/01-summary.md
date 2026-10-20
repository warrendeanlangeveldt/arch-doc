# summary

We ask the {p:forums.design_authority.name} to approve the Parcel Tracking Solution for build, so that customers can see where their parcel is within a minute of each scan and hear from us when delivery is due. The design runs on the Northwind Platform and cannot go live before the platform does.

## scope

This design covers the first release of parcel tracking: depot scans and carrier updates in, one timeline per parcel, a tracking API for the customer website and customer service, customer notifications by email and SMS, an operations dashboard for stalled parcels, and monitoring that raises incidents in {p:systems.itsm.name}. It ends at the Northwind Platform's published interfaces, which {dep:NP:integration/contracts} defines. Section {sec:context/in-scope} itemises the scope.

## decision-sought

REGISTER decision-request

DRQ-03 goes to the privacy and data forum first, because the eighteen-month history (ADR-02) needs its approval before the design review can approve the design that depends on it.

## overview

Customers today see yesterday's scans on a lookup page fed by a nightly file, and customer service checks carrier portals by hand. We replace that with event-driven tracking: depots publish each scan as it happens, carriers A and C push their updates, carrier B is polled, and the tracking service keeps one timeline per parcel. The tracking API serves the website and the customer service workspace, and our own notification service tells customers when the status changes.

We depend on the Northwind Platform for events, API publication, workflows, secrets and telemetry ({dep:NP}). The platform plans to reach production in late January 2027; our cutover starts on 1 March, and a go/no-go on 1 February decides whether that holds (RSK-07, DRQ-04).

{count:risk where rating=high|extreme} risks are rated high or extreme ({ids:risk where rating=high|extreme}). The extreme one is that public lookups reveal other people's parcels to anyone guessing numbers; requiring the postcode treats it (ADR-04). Carrier B cannot send webhooks before 2028, so we poll it against the reference architecture (EXC-01). The messaging provider contract is not signed (DEP-03), and without it there are no notifications at go-live.
