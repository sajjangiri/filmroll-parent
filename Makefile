.DEFAULT_GOAL := help

# The Docker stack, its config and its tests live in backend/, which is its own
# repo. These targets forward there so the usual commands still work from the
# workspace root. Variables pass through: make revision m="add shots".
BACKEND_TARGETS := up down clean build logs ps migrate revision redevelop test test-fast lint fmt shell psql

.PHONY: help
help: ## Show available targets
	@$(MAKE) --no-print-directory -C backend help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | grep -v '^help:' \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

.PHONY: $(BACKEND_TARGETS)
$(BACKEND_TARGETS):
	@$(MAKE) --no-print-directory -C backend $@

.PHONY: mobile
mobile: ## Start the Expo app (host create + guest camera)
	cd mobile && npm start
