# security

The platform's security rests on one identity per workload, private networking and an audit trail nobody can change. The residual risk we carry into production is in the access model and in security monitoring, neither of which is in place yet.

## views

We do not draw a control traceability view (EXC-03). The control register below traces each control to the risks it treats.

## identity

Users sign in through the {p:systems.identity.name}; workloads use their own workload identities, federated with it. Producing teams approve access to their topics and APIs, and access is recertified quarterly.

REGISTER control where area=identity

## privileged-access

REGISTER control where area=privileged-access

Break-glass is not tested yet, and its evidence is open (CTL-04). Production access is not ready until it is (RDY-07).

## data-protection

REGISTER control where area=data-protection

## network-security

REGISTER control where area=network

## monitoring

REGISTER control where area=monitoring

Security events will be collected from day one. Until security operations onboards them (DEP-03), nobody is watching them, and we would learn of misuse late.

## residual-risk

REGISTER risk where category=security cols id,title,rating,mitigation,residual,owner,status

The security architect accepts the residual ratings above on behalf of the platform. RSK-06 is accepted under the exception EXC-02.
