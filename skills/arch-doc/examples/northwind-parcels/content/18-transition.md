# transition

We cut over in March 2027, one depot first, then the carriers, then every depot, then the customer-facing switches. The legacy lookup keeps running until every depot publishes scans, so each step until the last can be undone.

## views

We do not draw a release scope view (EXC-05). {fig:cutover-plan} shows the cutover on a timeline.

## cutover

REGISTER cutover-step

FIGURE cutover-plan | Cutover, hypercare and the legacy lookup's read-only period

## rollback

| Failure | Trigger | Rollback action | Owner | Longest it may take |
|---|---|---|---|---|
| Pilot depot scans do not arrive or arrive out of order | Scan-to-visible over target for an hour at the pilot depot | Pilot depot stops publishing; the nightly file still runs | Depot operations manager | 30 minutes |
| Carrier webhooks fail | Webhook error rate over 5% | Carriers point back to the test endpoint; agents use portals | Integration lead | 2 hours, on the carriers' side |
| All-depot load exceeds what we tested | Ingest lag over 15 minutes | Depots added since the pilot stop publishing | Depot operations manager | 1 hour |
| Lookups fail after the website switch | ALT-02 at critical | Website switches back to the legacy lookup link | Digital channels lead | 15 minutes |
| Notifications go to the wrong person or too often | Any confirmed wrong recipient | Notifications switched off | Product owner | 5 minutes |

After CUT-08 the nightly file stops and there is no way back to the legacy lookup for new parcels.

## hypercare

Hypercare runs from 26 March to 23 April 2027. The parcels digital team staffs it from 07:00 to 19:00 every day, beside Parcels Tracking Support. Issues reach it as incidents in the Parcels Tracking Support group, which the build team watches. It reports daily to the Head of Parcels for two weeks, then twice a week.

## hypercare-exit

REGISTER acceptance-item where stage=hypercare-exit

## handover

REGISTER readiness-item where area=handover
