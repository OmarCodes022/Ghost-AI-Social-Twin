REGION ?= eu-west-1
ENV    ?= dev

.PHONY: build deploy-dev deploy-prod migrate layer-install test update db contact remember me show contacts telegram-webhook

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

# Fast code push — zips each handler.py and updates Lambda directly (no SAM/CloudFormation).
# Use this when only function handlers changed.
# Use deploy-dev when layer code (models.py, db.py, etc.) or template.yaml changed.
update:
	@echo "Pushing handler code to all ghost-*-$(ENV) functions..."
	@for dir in functions/*/; do \
		fn=$$(basename $$dir); \
		fn_name=ghost-$$(echo $$fn | tr '_' '-')-$(ENV); \
		echo "  → $$fn_name"; \
		zip -jq /tmp/ghost_$$fn.zip $$dir/handler.py && \
		aws lambda update-function-code \
			--function-name $$fn_name \
			--zip-file fileb:///tmp/ghost_$$fn.zip \
			--region $(REGION) \
			--output text --query 'LastModified'; \
	done
	@echo "All functions updated."

# Register the Telegram webhook URL with Telegram (run once after deploy)
telegram-webhook:
	@URL=$$(aws cloudformation describe-stacks --stack-name ghost-$(ENV) --region $(REGION) \
		--query "Stacks[0].Outputs[?OutputKey=='WebhookUrl'].OutputValue" --output text \
		| sed 's|/webhook|/telegram|') && \
	TOKEN=$$(aws ssm get-parameter --name /ghost/$(ENV)/telegram/bot_token \
		--with-decryption --query Parameter.Value --output text --region $(REGION)) && \
	echo "Registering: $$URL" && \
	curl -s "https://api.telegram.org/bot$$TOKEN/setWebhook?url=$$URL" | python3 -m json.tool

# Drop into a live psql session against the dev DB
db:
	@DSN=$$(aws ssm get-parameter \
		--name /ghost/dev/db/connection_string \
		--with-decryption --query Parameter.Value --output text --region $(REGION)) && \
	PGSSLMODE=require psql "$$DSN"

# ── Ghost admin ────────────────────────────────────────────────────────────────
# Set a contact's name, tier, notes (any combo)
# Usage: make contact PHONE=33744746977 NAME="Alice" TIER=1 NOTES="works at Google"
contact:
	@.venv/bin/python scripts/admin.py contact --phone "$(PHONE)" \
		$(if $(NAME),--name "$(NAME)") \
		$(if $(TIER),--tier "$(TIER)") \
		$(if $(NOTES),--notes "$(NOTES)")

# Add a memory about a contact
# Usage: make remember PHONE=33744746977 TEXT="Has a dog called Max"
remember:
	@.venv/bin/python scripts/admin.py remember --phone "$(PHONE)" --text "$(TEXT)"

# Add identity data about yourself (used in every response prompt)
# Usage: make me TEXT="I hate small talk. I never use exclamation marks."
me:
	@.venv/bin/python scripts/admin.py me --text "$(TEXT)"

# Show everything about a contact
# Usage: make show PHONE=33744746977
show:
	@.venv/bin/python scripts/admin.py show --phone "$(PHONE)"

# List all contacts
contacts:
	@.venv/bin/python scripts/admin.py contacts

# Ingest a WhatsApp exported .txt file for a contact
# Usage: make ingest FILE=exports/alice.txt PHONE=33744746977 NAME="Alice"
# Optional: MY_NAME="Omar" (default), DRY_RUN=1 to preview without writing
ingest:
	@.venv/bin/python scripts/ingest_whatsapp.py \
		--file "$(FILE)" \
		--phone "$(PHONE)" \
		$(if $(NAME),--name "$(NAME)") \
		$(if $(MY_NAME),--my-name "$(MY_NAME)") \
		$(if $(DRY_RUN),--dry-run)

# Run unit tests
test:
	python -m pytest tests/unit/ -v
