# service-processes

The service processes have to know the platform exists before the first consumer goes live. Incident, change and request are in progress. Major incident, knowledge, event and configuration practices have not started.

## views

The operational support view is not drawn (EXC-04).

## itil-readiness

REGISTER process-readiness

## incident

REGISTER process-readiness where process=incident cols id,design,evidence,owner,status

Incidents are raised against the application service of the interface that failed. A consumer's own fault goes to the consumer team first, and the platform support group is pulled in only when the platform is the cause.

## change

REGISTER process-readiness where process=change cols id,design,evidence,owner,status

Template releases are standard changes once three have gone through cleanly as normal changes. Broker and gateway configuration stays a normal change, approved by the {p:forums.change.short}, because a mistake there reaches every consumer.

## request

REGISTER process-readiness where process=request cols id,design,evidence,owner,status

## knowledge

REGISTER process-readiness where process=knowledge cols id,design,evidence,owner,status

The service desk needs two articles on day one: how to recognise a platform fault, and how to route it. Neither is written.
