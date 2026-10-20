# summary
We ask the **Architecture Review Board** to approve the depot scanning design for build. It depends on {dep:NP} for hosting and identity.

## scope
The design covers handheld scanning in the four metropolitan depots and the event feed to parcel tracking. Rural depots join in a later release, date TBC: Depot operations lead.

## decision-sought
REGISTER decision-request

## overview
The design has {count:risk} risks, {count:risk where rating=high} of them rated high. Two choices are still open:

- the handheld vendor, TBC: Procurement
- whether offline scans are replayed in order or by timestamp
  - ordering is cheaper but wrong across depots
  - timestamps need synchronised clocks
- the retention period for raw scan events, TBC

1. Approve the logical design.
2. Endorse the build plan in {sec:risks/dependencies}.
