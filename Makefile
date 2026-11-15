PYTHON ?= python3
CTL = $(PYTHON) k8sctl.py
.PHONY: help check adopt up create start stop status doctor diagnose test monitor reset-k8s destroy unit-test
help:
	@$(CTL) --help
check:
	@$(CTL) preflight
adopt:
	@$(CTL) adopt
up:
	@$(CTL) up
create:
	@$(CTL) create
start:
	@$(CTL) start
stop:
	@$(CTL) stop
status:
	@$(CTL) status
doctor:
	@$(CTL) doctor
diagnose:
	@$(CTL) diagnose
test:
	@$(CTL) test
monitor:
	@$(CTL) monitor
unit-test:
	@$(PYTHON) -m unittest discover -s tests -v
reset-k8s:
	@$(CTL) reset-k8s
destroy:
	@$(CTL) destroy
