# infrastructure

The platform runs as managed services in the organisation's cloud, one isolated zone per environment (ADR-01). Production runs in the primary region with its broker replicated to the paired region.

## views

VIEW platform-deployment | Northwind Platform: zones and regions | infrastructure

## hosting

| Component | Hosting | Development and test | Pre-production | Production | Hosting owner |
|---|---|---|---|---|---|
| API gateway | Managed gateway service | Single instance | Zone-redundant | Zone-redundant | Platform engineering lead |
| Event broker | Managed broker service | Single instance | Zone-redundant, replicated | Zone-redundant, replicated to the paired region | Platform engineering lead |
| Workflow runtime | Managed workflow service | Single instance | Zone-redundant | Zone-redundant | Platform engineering lead |
| Secrets store | Managed secrets service, hardware-backed keys | Shared tier | Premium tier | Premium tier | Security architect |
| Platform portal | Managed container runtime | Minimum scale | Zone-redundant | Zone-redundant, scaled on load | Platform product manager |
| Telemetry pipeline | Collector agents in each zone | One per zone | One per zone | One per zone and region | Platform engineering lead |

## network

| Source | Destination | Protocol | Direction | Purpose | Control |
|---|---|---|---|---|---|
| Consumer workloads | Platform services | HTTPS, AMQP over TLS | Inbound to the platform | Publish, subscribe, read secrets, start workflows | Private endpoints only (CTL-07) |
| Partners | API gateway | HTTPS | Inbound from the internet | Partner APIs | Web application firewall policy (CTL-08) |
| Platform services | Identity provider | HTTPS | Outbound | Token issue and validation | Hub egress allow-list |
| Telemetry pipeline | Monitoring platform | HTTPS | Outbound | Telemetry export | Hub egress allow-list |
| Production zone | Paired region production zone | Broker replication | Outbound | Disaster recovery | Hub-to-hub peering |

Every zone reaches the others only through the shared hub, which is why its failure stops every consumer (RSK-01).

## deployment

FIGURE promotion-path | How a release moves from development to production

Every deployable item, platform or consumer, reaches each zone through the {p:systems.cicd.name}, using the pipeline's own workload identity (DEP-02). A release reaches production only after its contract, load and failover tests pass and the change is approved. A failed health check rolls the release back to the last good version automatically. The platform engineering lead owns the pipeline templates.

## environment-config

The environments in {sec:application/environments} share one template set and differ only in scale, redundancy and data. Development and test hold synthetic data only. Pre-production holds masked copies on request, deleted after 14 days. Production alone has replication to the paired region, premium secrets tiers and break-glass accounts.
