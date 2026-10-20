# runbooks

{count:runbook where outcome=pass} of the {count:runbook} runbooks support needs have passed a test. The broker failover, manual onboarding and stuck workflow runbooks are not tested, and the secret rotation test failed.

## required

REGISTER runbook

## acceptance

REGISTER runbook where tested=yes cols id,title,test_date,tester,outcome,status

RBK-04 failed its test on 16 October: one consumer's workload kept the old secret until it restarted. The security architect reruns it after the rotation notice event is in place.
