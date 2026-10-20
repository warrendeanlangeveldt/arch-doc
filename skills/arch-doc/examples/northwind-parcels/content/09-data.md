# data

The solution holds parcels, scans, carrier updates and the timelines built from them, and for a short time the customer contact that lets us notify. Contact data is the only personal data, and we keep it apart from everything else.

## views

VIEW pts-data | Parcel Tracking Solution: data access | crud

## scope

REGISTER data-object

## flows

REGISTER data-flow

The website never receives an address or a contact (DF-07). The notification service reads the contact from the store at send time rather than from the event, so a corrected contact takes effect at once (CTL-10).

## classification

| Data | Classification | Personal data | Privacy impact | Control |
|---|---|---|---|---|
| Parcel, scan, carrier update, timeline, exception | Internal | Destination postcode only | Low: a postcode alone identifies nobody | Public lookup needs the parcel number as well (CTL-08) |
| Customer contact | Confidential | Email address or mobile number | Medium: misuse would breach the privacy policy | Stored apart, encrypted, deleted 30 days after delivery (CTL-05); agent access logged (CTL-04) |
| Notification record | Confidential | The channel used, not the address | Low | Retention open (DAT-06) |

The privacy impact assessment goes to the privacy and data forum on 19 November (CHK-02).

## retention

Parcels, scans, carrier updates, timelines and exceptions stay online for eighteen months after delivery and are then deleted. That is six months longer than the retention standard allows, and needs EXC-02. Contacts are deleted 30 days after delivery by an expiry set when the delivered event lands. How long to keep notification records is open with the privacy officer. The data owner is accountable for the timeline data and the privacy officer for contacts.

## migration

We migrate no history (ADR-07). The legacy lookup stays read-only for parcels manifested before cutover, until 30 June 2027 (RET-01).

## quality

| Rule | Check | Owner | Passing |
|---|---|---|---|
| Every scan belongs to a manifested parcel | Unmatched scans counted on the dashboard; flagged after 12 hours | Depot operations manager | Under 0.1% of scans unmatched a day |
| Scan times carry a time zone | Ingest rejects scan times without an offset to a holding topic | Integration lead | No unordered timelines from firmware 4.2 handhelds after DEP-05 |
| Carrier codes map to our statuses | Unmapped codes logged and alerted daily | Integration lead | Zero unmapped codes for a week before cutover |
| Daily reconciliation with the depot system | Count of parcels manifested against parcels tracked | Data owner | Counts agree each day |
