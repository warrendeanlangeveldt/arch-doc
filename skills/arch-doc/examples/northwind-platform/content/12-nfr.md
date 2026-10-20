# nfr

Each non-functional requirement in {sec:requirements/nfrs} has a design response and a test. Most tests run in pre-production, which is late (ISS-01), so most targets are designed and not yet proven.

## views

We do not draw an NFR traceability view (EXC-03). Each NFR names its own test and evidence.

## availability

REGISTER nfr where category=availability cols id,title,target,response,test,status

## performance

REGISTER nfr where category=performance cols id,title,target,response,test,status

## scalability

REGISTER nfr where category=scalability cols id,title,target,response,test,status

The limit is the broker's throughput tier. Raising it takes a planned change of about an hour, so we raise it on a schedule before known peaks instead of on demand.

## resilience

REGISTER nfr where category=resilience cols id,title,target,response,test,status

The failover runbook (RBK-02) is not yet tested. Until it is, the recovery time objective is a design figure, not a demonstrated one.

## supportability

REGISTER nfr where category=supportability cols id,title,target,response,evidence,status

## observability

REGISTER nfr where category=observability cols id,title,target,response,test,status

Alerts and the runbooks they lead to are in {sec:monitoring/coverage}.
