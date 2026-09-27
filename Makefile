test:
	python -m pytest -q

test-domain:
	python -m pytest -q tests/domain

test-api:
	python -m pytest -q tests/api

test-agent:
	python -m pytest -q tests/agent

test-web:
	cd apps/web && npm run test

typecheck-web:
	cd apps/web && npm run typecheck

build-web:
	cd apps/web && npm run build

test-all: test-domain test-api test-agent test-web typecheck-web build-web

.PHONY: test test-domain test-api test-agent test-web typecheck-web build-web test-all
