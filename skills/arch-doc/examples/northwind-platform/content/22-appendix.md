# appendix

## glossary

REGISTER glossary-term

## required-views

| Diagram or view | Required | Purpose | Source |
|---|---|---|---|
| {view:current-landscape} Integration today | Yes | Shows what the platform replaces | diagrams/current-landscape.ead |
| {view:platform-layered} Layered view | Yes | The platform between consumers and organisation services | diagrams/platform-layered.ead |
| {fig:platform-overview} Platform overview | Yes | The whole target design on one page | diagrams/platform-overview.mmd |
| {view:platform-components} Components | Yes | The components and the interfaces they publish | diagrams/platform-components.ead |
| {view:platform-cooperation} Application cooperation | Yes | How consumers and organisation services meet the platform | diagrams/platform-cooperation.ead |
| {fig:event-delivery} Event delivery | Yes | Retry, dead-letter and replay | diagrams/event-delivery.mmd |
| {view:platform-data} Data access | Yes | Which component reads and writes which data | diagrams/platform-data.ead |
| {view:platform-deployment} Zones and regions | Yes | Where the platform runs | diagrams/platform-deployment.ead |
| {fig:promotion-path} Promotion path | Yes | How a release reaches production | diagrams/promotion-path.mmd |
| Traceability, operational support, release scope and retirement views | No | Not drawn; see EXC-03, EXC-04 and EXC-05 | None |

## object-guide

CATALOGUE

Application components stand for the platform, its components and the organisation services it uses, one for each application or component record. Application interfaces are the published interfaces. Data objects match the data object register one for one. Nodes are zones, system software the managed services, and locations the two regions.
