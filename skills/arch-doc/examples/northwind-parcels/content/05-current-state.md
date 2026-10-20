# current-state

Tracking today is a day behind. The handhelds upload scans to the depot operations system, a nightly file copies them to a lookup page, and anything a partner carrier knows reaches us only when an agent logs into its portal.

## views

VIEW pts-current | Tracking today: application landscape | application-landscape

## business-context

REGISTER capability where state=current|both cols id,title,description,state,status

Parcel tracking exists, but a customer sees yesterday's scans, and a parcel handed to a partner carrier disappears from it. Customer service answers most tracking calls by phoning the carrier, at about four minutes a call. Nobody looks for parcels that have stopped moving until the customer calls.

## application-landscape

REGISTER application where state=current|both cols id,title,purpose,hosting,lifecycle,owner

## integration-landscape

REGISTER integration where state=current cols id,title,source,target,pattern,trigger,failure

When the nightly file fails, the lookup page shows the day before's scans and nothing says so. Customer service finds out from the first confused customer.

## support-model

Customer service owns the legacy lookup, and one engineer in the depot systems team keeps the nightly transfer running in business hours. Nothing monitors either. Carrier status has no system owner at all: it lives in agents' browsers.
