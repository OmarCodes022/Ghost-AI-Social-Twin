REGION ?= eu-west-1
ENV    ?= dev

.PHONY: build deploy-dev deploy-prod migrate layer-install test

# Build all Lambda functions and layers
build:
	sam build --parallel

# Deploy to dev (no confirmation prompt)
deploy-dev: build
	sam deploy \
		--stack-name ghost-dev \
		--region $(REGION) \
		--capabilities CAPABILITY_IAM \
		--resolve-s3 \
		--s3-prefix ghost \
		--parameter-overrides Env=dev \
		--no-confirm-changeset

# Deploy to prod (requires confirmation)
deploy-prod: build
	sam deploy \
		--stack-name ghost-prod \
		--region $(REGION) \
		--capabilities CAPABILITY_IAM \
		--resolve-s3 \
		--s3-prefix ghost \
		--parameter-overrides Env=prod \
		--confirm-changeset

# Run Alembic migrations against the target DB.
# Fetch the connection string from SSM first:
#   export DATABASE_URL=$(aws ssm get-parameter \
#     --name /ghost/db/connection_string \
#     --with-decryption --query Parameter.Value --output text)
migrate:
	@if [ -z "$(DATABASE_URL)" ]; then \
		echo "❌  DATABASE_URL is not set."; \
		echo "    Run: export DATABASE_URL=\$$(aws ssm get-parameter --name /ghost/dev/db/connection_string --with-decryption --query Parameter.Value --output text)"; \
		exit 1; \
	fi
	cd migrations && DATABASE_URL=$(DATABASE_URL) ../.venv/bin/alembic upgrade head

# Install layer dependencies for local development (Linux-compatible wheels).
# Uses manylinux2014 platform so the binaries work in Lambda (Amazon Linux 2).
layer-install:
	pip install \
		-r layers/ghost_common/requirements.txt \
		--target layers/ghost_common/python \
		--platform manylinux2014_x86_64 \
		--implementation cp \
		--only-binary=:all: \
		--python-version 3.12 \
		--upgrade

# Run unit tests
test:
	python -m pytest tests/unit/ -v
