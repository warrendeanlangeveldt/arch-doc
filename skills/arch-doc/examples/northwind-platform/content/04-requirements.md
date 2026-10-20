# requirements

The requirements come from the technology strategy, a survey of consumer teams, an internal audit finding and the review of the June 2026 manifest outage. The quality targets are stated here; {ch:nfr} shows how the design meets them.

## business-requirements

REGISTER business-requirement

## functional-requirements

REGISTER functional-requirement

FR-08 (schema checks at publish) is a should. Until it is built, RSK-04 stays rated high.

## nfrs

REGISTER nfr

## views

We do not draw requirement traceability, business outcome or capability views. The model holds no motivation elements, and the registers carry each trace (EXC-03).

## assumptions

REGISTER assumption

ASM-02 matters most. If peak volume passes 5,000 events per second before the 2027 peak season, the broker needs resizing before the platform has a year of production history to size it from.

## constraints

REGISTER constraint

## dependencies

REGISTER dependency cols id,title,provider,required_by,status

Delivery status and the impact of each dependency arriving late are tracked in {sec:risks/dependencies}.
