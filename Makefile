PYTHON ?= python3
CTL = $(PYTHON) k8sctl.py
.PHONY: help check adopt context use-context up create start stop status doctor diagnose test monitor reset-k8s destroy unit-test docs-check validate install-cli uninstall-cli
help:
	@$(CTL) --help
check:
	@$(CTL) preflight
adopt:
	@$(CTL) adopt
context:
	@$(CTL) context status
use-context:
	@$(CTL) context use
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
docs-check:
	@$(PYTHON) scripts/check_markdown.py
validate:
	@ruff check k8sctl.py scripts/check_markdown.py tests
	@$(PYTHON) -m py_compile k8sctl.py scripts/check_markdown.py
	@bash -n scripts/guest/prepare-node.sh scripts/host/*.sh
	@$(PYTHON) scripts/check_markdown.py
	@$(PYTHON) -m unittest discover -s tests -v
	@git diff --check
install-cli:
	@scripts/host/install-cli.sh --install
uninstall-cli:
	@scripts/host/install-cli.sh --uninstall
reset-k8s:
	@$(CTL) reset-k8s
destroy:
	@$(CTL) destroy
