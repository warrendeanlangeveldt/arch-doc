# service-processes

Incident, change and knowledge are in progress. Major incident, request, event and configuration have not started, and all of them wait on the service owner.

## views

The operational support view is not drawn (EXC-04).

## itil-readiness

REGISTER process-readiness

## incident

REGISTER process-readiness where process=incident cols id,design,evidence,owner,status

Incidents for this service carry the category Parcels and subcategory Tracking and are raised against the Parcel Tracking (production) application service. Priority follows the standard impact and urgency matrix; a public lookup outage is high impact. A major incident is declared when lookups or scan intake are down for 15 minutes in business hours.

## change

REGISTER process-readiness where process=change cols id,design,evidence,owner,status

Application releases through the pipeline become standard changes once the template is approved by the {p:forums.change.short}. Store schema, route and secret changes stay normal changes, with a two-day lead time. Emergency changes follow the standard emergency path.

## request

REGISTER process-readiness where process=request cols id,design,evidence,owner,status

Both catalogue items must exist at go-live; without dashboard access, depots cannot work their stalled parcels.

## knowledge

REGISTER process-readiness where process=knowledge cols id,design,evidence,owner,status

The service desk and agents need three articles on day one, in the Parcels knowledge base: reading a timeline, what each status means, and when to escalate a stalled parcel. The customer service manager owns them; agents read them in their workspace. The first two support first-call resolution of tracking enquiries.
