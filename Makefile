test:
	python -m pytest -q

test-web:
	cd apps/web && npm run test

build-web:
	cd apps/web && npm run build

test-all: test test-web build-web

.PHONY: test test-web build-web test-all
