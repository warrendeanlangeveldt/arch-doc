# application
The tracking service runs on {dep:NP}, version 0.2. {ids:application where state=target} are in scope.

## views
{view:app-context} shows the tracking service among its users and neighbours.

VIEW app-context | Tracking application context | application-context

## scope
REGISTER application where state=target

## components
We build {count:component} components on the platform's event broker.

REGISTER component

## environments
REGISTER environment

The secret store holds four secrets.

## channels
People take part at five points:

| Point | Who | What they do |
|---|---|---|
| Booking | Customer | Books a delivery |
| Collection | Driver | Scans the parcel |
| Depot | Depot staff | Sorts the parcel |
| Delivery | Driver | Confirms delivery |
| Enquiry | Customer service | Answers questions |

{fig:access} shows who reads and writes tracking data.

FIGURE access | Access to tracking data

| Role | Data | Access |
|---|---|---|
| Depot staff | Scan events | read-write |
| Customer service | Tracking history | read |
