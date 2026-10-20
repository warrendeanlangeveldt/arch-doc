# target

The target tracks every parcel from the moment its manifest closes to its delivery, from depot scans and carrier updates, and tells customers before they ask.

## views

VIEW pts-layered | Parcel Tracking Solution: layered view | solution-context

## description

REGISTER capability where state=target|both cols id,title,description,realised_by

Depot handhelds publish each scan through the platform, and the depot operations system publishes each manifest. Carriers A and C push status by webhook; carrier B is polled. The tracking service orders everything by event time into one timeline per parcel and derives the parcel's status. Customers look parcels up on the website with the parcel number and postcode; agents see the full timeline in {p:systems.itsm.name}. Each status change goes to the customer by email or SMS, and parcels that stop moving appear on the ops dashboard.

The solution uses the platform's event, API publication, workflow and secret interfaces and its telemetry stream ({dep:NP:integration/contracts}). It holds no queues, gateways or credentials of its own.

## diagram

FIGURE pts-overview | Parcel tracking: event sources, the solution and the people and systems that use it

Read the figure left to right: where events come from, what the solution does with them, and who sees the result.

## principles

| Principle | Source | What it means here |
|---|---|---|
| Event time, not arrival time | Parcels design principle | A buffered scan lands in its true place in the timeline (RSK-01) |
| Platform interfaces only | Northwind Platform design | No direct broker, gateway or vault access (ACC-04) |
| Personal data apart and short-lived | Privacy policy | Contacts live apart from the timeline and go 30 days after delivery (BR-05) |
| Push where offered, poll only where not | Integration reference architecture | Webhooks for carriers A and C; carrier B polled under EXC-01 |

## operating-model

Customer service stops phoning carriers for status and reads the timeline instead, which changes its call scripts and training. Depot operations takes on the stalled-parcel queue on the dashboard, a new daily task for each depot's duty manager. A new support team, Parcels Tracking Support, takes incidents from {p:systems.monitoring.name}; it does not exist yet (RDY-02). The depot systems team stops running the nightly transfer.
