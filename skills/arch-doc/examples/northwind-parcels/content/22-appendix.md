# appendix

## glossary

REGISTER glossary-term

## required-views

| Diagram or view | Required | Purpose | Source |
|---|---|---|---|
| {view:pts-current} Tracking today | Yes | What the solution replaces | diagrams/pts-current.ead |
| {view:pts-layered} Layered view | Yes | Users, the solution and the platform it runs on | diagrams/pts-layered.ead |
| {fig:pts-overview} Overview | Yes | The whole design on one page | diagrams/pts-overview.mmd |
| {view:pts-components} Components | Yes | The components and how data moves between them | diagrams/pts-components.ead |
| {fig:parcel-status} Parcel statuses | Yes | The status rules the tracking service applies | diagrams/parcel-status.mmd |
| {view:pts-integration} Integrations | Yes | Every system we exchange data with | diagrams/pts-integration.ead |
| {fig:scan-journey} Scan journey | Yes | A scan from the handheld to the customer | diagrams/scan-journey.mmd |
| {view:pts-data} Data access | Yes | Which component reads and writes which data | diagrams/pts-data.ead |
| {view:pts-deployment} Production deployment | Yes | Where the solution runs | diagrams/pts-deployment.ead |
| {fig:cutover-plan} Cutover plan | Yes | The cutover and hypercare on a timeline | diagrams/cutover-plan.mmd |
| Traceability, operational support, release scope and retirement views | No | Not drawn; see EXC-03, EXC-04 and EXC-05 | None |

## object-guide

CATALOGUE

Application components stand for the solution, its components and the applications it exchanges data with, one for each application or component record. Application interfaces are the platform interfaces we use, which belong to the platform design, and carrier B's API. Business actors are the people who use the solution. Data objects match the data object register one for one. The technology objects are the production zone, its runtime and database, the replica and the subnet.
