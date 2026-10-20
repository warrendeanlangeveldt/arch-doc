# risks

The risks a reviewer must weigh are support staffing (RSK-02) and schema changes without a registry (RSK-04). The late pre-production zone (ISS-01) is already a problem, not a risk.

## architecture-risks

REGISTER risk where category=architecture cols id,title,likelihood,impact,rating,mitigation,owner,status

## operational-risks

REGISTER risk where category=operational cols id,title,rating,mitigation,residual,owner,status

RSK-02 cannot be mitigated inside the design: it needs people. DRQ-03 asks the steering group to accept it with the interim roster in place, or to fund earlier hiring.

## issues

REGISTER issue

## dependencies

REGISTER dependency

DEP-04 is at risk. Without configuration record classes for platform services, incidents cannot be raised against the platform at go-live, and alerts would page engineers directly with no record.
