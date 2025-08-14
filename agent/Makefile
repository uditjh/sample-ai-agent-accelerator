app := agentcore_helloworld

all: help

.PHONY: help
help: Makefile
	@echo
	@echo " Choose a make command to run"
	@echo
	@sed -n 's/^##//p' $< | column -t -s ':' |  sed -e 's/^/ /'
	@echo

## init: initialize a new python project
.PHONY: init
init:
	python -m venv .venv
	direnv allow .

## install: add a new package (make install <package>), or install all project dependencies from piplock.txt (make install)
.PHONY: install
install:
	python -m pip install --upgrade pip
	@if [ -z "$(filter-out install,$(MAKECMDGOALS))" ]; then \
		echo "Installing dependencies from piplock.txt"; \
		pip install -r piplock.txt; \
	else \
		pkg="$(filter-out install,$(MAKECMDGOALS))"; \
		echo "Adding package $$pkg to requirements.txt"; \
		grep -q "^$$pkg$$" requirements.txt || echo "$$pkg" >> requirements.txt; \
		pip install $$pkg; \
		pip install -r requirements.txt; \
		pip freeze > piplock.txt; \
	fi

# Empty rule to handle package name argument
%:
	@:

## start: run local project
.PHONY: start
start:
	clear
	@echo ""
	python -u main.py

## run: run uvicorn app
.PHONY: run
run:
	KNOWLEDGE_BASE_ID=${kb_id} uv run uvicorn main:app --host 0.0.0.0 --port 8080

## test: test the invocations endpoint
.PHONY: test
test:
	curl -X POST http://localhost:8080/invocations -H "Content-Type: application/json" -d '{ "input": {"prompt": "What is artificial intelligence?"} }'

## build: build container image
.PHONY: build
build:
	docker buildx build --platform linux/arm64 -t $(app):arm64 --load .

## docker-run: run container image
.PHONY: docker-run
docker-run: build
	docker run --platform linux/arm64 -p 8080:8080 \
		-e AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID}" \
		-e AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY}" \
		-e AWS_SESSION_TOKEN="${AWS_SESSION_TOKEN}" \
		-e AWS_REGION="${AWS_REGION}" \
		-e APP_NAME="${app}" \
		-e KNOWLEDGE_BASE_ID="${kb_id}" \
		$(app):arm64

## deploy: deploy the agentcore agent (make deploy app=my-app)
.PHONY: deploy
deploy:
	./deploy.sh ${app} ${kb}

## run-client: run test client
.PHONY: run-client
run-client:
	python -u client.py --agent_runtime_arn=$(shell cat ./agent_runtime_arn)
