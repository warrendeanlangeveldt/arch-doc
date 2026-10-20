# current-state

Teams integrate today through whatever each one built. Nothing is shared, so nothing is watched in one place, and a change in one team's system breaks another's without warning.

## views

VIEW current-landscape | Integration today: application landscape | application-landscape

## business-context

REGISTER capability where state=current|both cols id,title,description,state,status

File exchange works, slowly: data is a day old when it arrives, and a failed file is found the next morning by the people waiting for it. Integration management and secrets management exist only inside each team, with no shared standard.

## application-landscape

REGISTER application where state=current|both cols id,title,purpose,hosting,lifecycle,owner

The team-run queues have no single owner today. The platform product manager confirms an owner for each before its team migrates.

## integration-landscape

REGISTER integration where state=current cols id,title,source,target,pattern,trigger,failure

The direct database reads are the worst of these. A schema change in one team's system silently breaks every reader, and there is no list of who reads what.

## support-model

Each team supports its own integrations in business hours. The legacy file exchange has one support engineer and no runbook for a failed transfer beyond a manual rerun. Nobody monitors the integrations end to end, so the June 2026 manifest outage ran for nine hours before a depot reported it.
