# infrastructure

The solution runs as containers and one document database in the Northwind Platform's zones on Azure, one resource group per environment. Production runs in the Azure primary region, with the database replicated to the paired region.

## views

VIEW pts-deployment | Parcel Tracking Solution: production deployment | infrastructure

## hosting

| Component | Hosting | Region | Production scale | Owner |
|---|---|---|---|---|
| Scan ingest, webhook receiver, tracking service, tracking API, notification service, ops dashboard | Containers in rg-pts-prd on the platform's container runtime | Azure primary region | 2 to 30 replicas each, scaled on queue depth or requests | Integration lead |
| Carrier poller and exception workflows | Workflows on the platform's workflow interface | Azure primary region | One schedule; one timer per parcel | Solution architect |
| Tracking store | Managed document database pts-prd-tracking-db, zone-redundant, autoscaling | Azure primary region, replica in the paired region | Autoscale to 20,000 operations a second | Data owner |
| Monitors and dashboards | {p:systems.monitoring.name} | Vendor-hosted | Not applicable | Service owner |

## network

| Source | Destination | Protocol | Direction | Purpose | Control |
|---|---|---|---|---|---|
| Handhelds over depot networks and mobile data | Platform gateway, scan route | HTTPS | Inbound | Scans | Handheld client credentials |
| Carriers A and C, from their published ranges | Platform gateway, webhook route | HTTPS | Inbound | Status webhooks | Signature and source allow-list (CTL-07) |
| snet-pts-prd, 10.42.16.0/24 | Carrier B API | HTTPS | Outbound through the platform hub | Polling | Egress allow-list for carrier B's hostname |
| snet-pts-prd | pts-prd-tracking-db private endpoint, 10.42.16.64/27 | TLS | Internal | Store access | Private endpoint; no public access |
| snet-pts-prd | Messaging provider | HTTPS | Outbound through the platform hub | Notifications | Egress allow-list for the provider's hostname |
| Customer website | Platform gateway, public tracking route | HTTPS | Inbound | Lookups | Rate limit and postcode (CTL-08) |

## deployment

Each container image is built from the pts repository in {p:systems.source_control.name} and deployed by {p:systems.cicd.name} with the platform's pipeline templates, using the pipeline's own platform identity. A release goes to development on merge, to test and pre-production on approval by the integration lead, and to production as a standard change once the template is approved (PRC-03). A release that fails its health checks rolls back to the previous image automatically. Store changes are normal changes, applied by the same pipeline with a backup taken first.

## environment-config

The environments in {sec:application/environments} use the same images and templates. Development and test use carrier sandboxes and synthetic contacts. Pre-production uses copies of production parcels with contacts replaced (CTL-06) and is the only place load and failover tests run. Production alone has the paired-region replica, client credentials for the real website and carriers, and the {p:systems.itsm.name} incident integration switched on.
