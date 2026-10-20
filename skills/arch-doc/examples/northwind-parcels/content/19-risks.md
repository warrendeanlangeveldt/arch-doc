# risks

The risks a reviewer must weigh are the public lookup (RSK-04) and our dependence on the platform's dates (RSK-07). Carrier B's missing webhooks are already an issue, not a risk.

## architecture-risks

REGISTER risk where category=architecture cols id,title,likelihood,impact,rating,mitigation,owner,status

## operational-risks

REGISTER risk where category=operational cols id,title,rating,mitigation,residual,owner,status

RSK-02 has no mitigation yet. The depot operations manager is asking the mobile carrier for coverage at the two regional depots; until there is an answer, those depots' tracking lags whenever their coverage drops.

## issues

REGISTER issue

## dependencies

REGISTER dependency

DEP-03 is at risk. Without the messaging provider, we go live without notifications and switch them on later as a separate change.
