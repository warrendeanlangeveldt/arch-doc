# lifecycle

The solution retires the legacy tracking lookup, the nightly scan file and the manual carrier checks. The lookup goes last, so agents can still see parcels manifested before cutover.

## views

We do not draw a retirement impact view (EXC-05). The register below names what retires, what replaces it and when.

## retired

REGISTER retired-component

## decommissioning

| Item | Action | Owner | Date | Evidence |
|---|---|---|---|---|
| Nightly scan file | Stop the job, remove the SFTP account and its key | Customer service manager | 2027-03-26 | Job and account removed |
| Legacy lookup link on the website | Remove the link | Digital channels lead | 2027-06-30 | Website release note |
| Legacy lookup database | Export to the archive, then destroy | Customer service manager | 2027-07-31 | Archive receipt and destruction certificate |
| Legacy lookup server | Shut down and dispose | Customer service manager | 2027-08-31 | Disposal certificate |
| Agent carrier portal logins | Revoke all but two per carrier for exceptions | Customer service manager | 2027-04-30 | Account list |
| CMDB records | Retire the legacy business application, its CIs and the file integration | Service owner | With each retirement | Record history |
