# runbooks

{count:runbook where outcome=pass} of the {count:runbook} runbooks support needs have passed a test. The restore runbook does not exist yet, and nobody has tested a carrier poller or messaging provider failure.

## required

REGISTER runbook

## acceptance

REGISTER runbook where tested=yes cols id,title,test_date,tester,outcome,status
