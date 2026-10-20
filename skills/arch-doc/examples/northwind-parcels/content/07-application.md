# application

The solution is one application of {count:component} components, built and owned by the parcels digital team. {count:application where change=changed} other applications change to work with it.

## views

VIEW pts-components | Parcel Tracking Solution: components | application-components

## scope

REGISTER application where state=target|both cols id,title,purpose,change,criticality,owner

## components

REGISTER component

FIGURE parcel-status | Parcel statuses the tracking service derives from the timeline

The carrier poller, notification service, dashboard and exception workflows are not started. All four are in release 1; the notification service is the one at risk, because it waits on the messaging provider contract (DEP-03).

## environments

REGISTER environment

Each environment is a resource group in the matching platform zone ({dep:NP:application/environments}). Pre-production and production are not ready, because the platform's own zones are not.

## channels

| User group | Channel | Sign-in | Access | Journeys that matter |
|---|---|---|---|---|
| Customers | Customer website | None | Parcel number and destination postcode | Where is my parcel; when will it arrive |
| Customers | Email and SMS | None | The contact on the manifest | Out for delivery; delivered; attempted |
| Customer service agents | {p:systems.itsm.name} workspace | {p:systems.identity.name} | Agent role in {p:systems.itsm.name} | Answer a tracking enquiry; open a claim |
| Depot and operations staff | Ops dashboard | {p:systems.identity.name} | Ops viewer or ops lead group (CTL-01) | Clear stalled parcels; spot a depot with no scans |
