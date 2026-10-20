# lifecycle

The platform retires the integration paths teams built for themselves. Nothing retires at go-live: each path closes when the last team using it has moved.

## views

We do not draw a retirement impact view (EXC-05). The register below names what retires, its replacement and when.

## retired

REGISTER retired-component

The date for retiring the batch jobs that move data between teams is open. The platform product manager sets it once every team using them has a migration date.

## decommissioning

| Item | Action | Owner | Date | Evidence |
|---|---|---|---|---|
| Team-run queue connection strings | Revoke each when its team moves (RSK-05) | Security architect | As each team moves, by 2027-06-30 | Revocation log |
| Legacy file exchange accounts | Disable partner and system accounts | Platform support lead | 2027-09-30 | Account report |
| Legacy file exchange server | Shut down, wipe and dispose | Platform support lead | 2027-10-31 | Disposal certificate |
| Batch scheduler jobs between teams | Remove each job and its credentials | Platform support lead | With RET-03 | Job list showing none remaining |
| Configuration records | Retire the application and job records | Platform support lead | With each retirement | Record history |
