# monitoring

We monitor in {p:systems.monitoring.name}: whether scans arrive, whether lookups work, whether notifications go, and whether anyone is trying to misuse the public route. Each alert raises an incident in {p:systems.itsm.name} against the Parcel Tracking application service.

## views

The operational support view is not drawn (EXC-04). {view:pts-integration} shows the path from the solution to {p:systems.monitoring.name} and {p:systems.itsm.name}.

## coverage

REGISTER alert

The lookup sweep alert has no runbook: it goes to security operations, who use their own procedure. The store capacity alert points at a restore runbook that is not written yet (RBK-07); the integration lead writes a capacity runbook before CHK-05.

## correlation

Monitors alert on the service, not on each replica, so a fault in one component raises one alert. {p:systems.monitoring.name} groups alerts for the same monitor into one incident and updates it rather than opening another (ADR-06). When the platform's event interface is down, our ingest and dead-letter alerts are suppressed in favour of the platform's own incident.

## event-mapping

| Event source | Event | Configuration item | Correlation rule | Assignment group |
|---|---|---|---|---|
| {p:systems.monitoring.name} APM, tracking API | Errors or latency | Parcel Tracking (production) application service | One incident per monitor | Parcels Tracking Support |
| {p:systems.monitoring.name}, scan ingest | Lag or dead-letter depth | Parcel Tracking (production) application service | One incident per monitor; suppressed during a platform incident | Parcels Tracking Support |
| {p:systems.monitoring.name}, notification service | Provider failures | Parcel Tracking (production) application service | One incident per monitor | Parcels Tracking Support |
| {p:systems.monitoring.name}, webhook receiver and gateway logs | Signature failures or lookup sweeps | Parcel Tracking (production) application service | One incident per monitor | Security operations |
| {p:systems.monitoring.name}, tracking service | Depot scan lag | The depot's location record | One incident per depot | Depot operations duty manager |

An event that binds to no CI is a gap; until DEP-04 creates the records, every one of these is.

## acceptance

REGISTER acceptance-item where stage=monitoring
