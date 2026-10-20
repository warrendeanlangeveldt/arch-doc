# security

The exposure that matters is the public lookup: parcel numbers are guessable, so without the postcode anyone could follow other people's deliveries. The rest of the design leans on the platform's identity, secrets and network controls ({dep:NP:security/identity}).

## views

We do not draw a control traceability view (EXC-03). Each control below names the risks it treats.

## identity

Staff sign in to the ops dashboard with {p:systems.identity.name}. Agents reach timelines through their {p:systems.itsm.name} roles. Customers do not sign in: the parcel number and postcode together are the key.

REGISTER control where area=identity

## privileged-access

REGISTER control where area=privileged-access

There is no break-glass account of our own; we use the platform's.

## data-protection

REGISTER control where area=data-protection

## network-security

REGISTER control where area=network

## monitoring

REGISTER control where area=monitoring

## residual-risk

REGISTER risk where category=security cols id,title,rating,mitigation,residual,owner,status

The security architect accepts the residual ratings above for the public lookup, and the privacy officer for notifications. RSK-04 stays rated extreme until CTL-08 is built and tested; until then the public route stays closed.
