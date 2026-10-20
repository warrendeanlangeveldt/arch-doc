# nfr

Every non-functional requirement in {sec:requirements/nfrs} has a design response and a test. None is proven yet: the tests run in pre-production, which the platform has not delivered.

## views

We do not draw an NFR traceability view (EXC-03).

## availability

REGISTER nfr where category=availability cols id,title,target,response,test,status

## performance

REGISTER nfr where category=performance cols id,title,target,response,test,status

The 60-second target depends on the platform's own delivery latency of under 500 ms ({dep:NP:nfr/performance}). Almost all of the budget is ours.

## scalability

REGISTER nfr where category=scalability cols id,title,target,response,test,status

The store's autoscale ceiling is the limit. At the peak rate it runs at about 60% of that ceiling, and we raise the ceiling before November if the September soak test shows less headroom (RSK-08).

## resilience

REGISTER nfr where category=resilience cols id,title,target,response,test,status

The restore runbook is not written (RBK-07). Until it is tested, the recovery time objective is a design figure.

## supportability

REGISTER nfr where category=supportability cols id,title,target,response,evidence,status

## observability

REGISTER nfr where category=observability cols id,title,target,response,test,status

Alerts, their thresholds and runbooks are in {sec:monitoring/coverage}.
