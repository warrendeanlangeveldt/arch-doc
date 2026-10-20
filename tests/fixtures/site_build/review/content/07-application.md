# application
The service has three components, shown in {fig:components}.

## components
REGISTER component

FIGURE components | Components of the depot scanning service and the platform services they use

| Concern | Choice | Why |
|---|---|---|
| Runtime | Container apps | The platform runs them; see {dep:NP} |
| Store | Event log plus read model | Replays need the raw order |
| Clock | Depot time server | TBC: Network team |
| Capacity | Peak load | {count:component} components sized for {ids:risk where category=architecture}; TBC: Capacity lead |

## views
VIEW scan-flow | Scan event flow from handheld to tracking | integration-flows

Every event carries the depot, the handheld and a sequence number. See `scan.v2` in the integration catalogue and [the event guide](https://example.com/events).
