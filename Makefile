REGION ?= eu-west-1
ENV    ?= dev
PYTHON ?= .venv/bin/python

.PHONY: build deploy-dev deploy-prod migrate layer-install test db-test update db contact remember me show contacts telegram-webhook mood send proactive dashboard dashboard-install thoughts convo

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

# Fast code push — zips all .py files in each function dir and updates Lambda directly.
# Use this when only function code changed (no layer or template.yaml changes).
update:
	@echo "Pushing handler code to all ghost-*-$(ENV) functions..."
	@for dir in functions/*/; do \
		fn=$$(basename $$dir); \
		fn_name=ghost-$$(echo $$fn | tr '_' '-')-$(ENV); \
		echo "  → $$fn_name"; \
		zip -jq /tmp/ghost_$$fn.zip $$dir/*.py && \
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
# Set a contact's name, tier, notes, preferred language, persona (any combo)
# Usage: make contact PHONE=33744746977 NAME="Alice" TIER=1 NOTES="works at Google" LANG="French"
# Usage: make contact PHONE=33744746977 PERSONA=lea PERSONA_NAME="Léa"
contact:
	@.venv/bin/python scripts/admin.py contact --phone "$(PHONE)" \
		$(if $(NAME),--name "$(NAME)") \
		$(if $(TIER),--tier "$(TIER)") \
		$(if $(NOTES),--notes "$(NOTES)") \
		$(if $(LANG),--lang "$(LANG)") \
		$(if $(PERSONA),--persona "$(PERSONA)") \
		$(if $(PERSONA_NAME),--persona-name "$(PERSONA_NAME)")

# Add a memory about a contact
# Usage: make remember PHONE=33744746977 TEXT="Has a dog called Max"
remember:
	@.venv/bin/python scripts/admin.py remember --phone "$(PHONE)" --text "$(TEXT)"

# Add identity data about yourself or a persona (used in every response prompt)
# Usage: make me TEXT="I hate small talk. I never use exclamation marks."
# Usage: make me TEXT="Je suis une fille de 22 ans..." PERSONA=lea
me:
	@.venv/bin/python scripts/admin.py me --text "$(TEXT)" \
		$(if $(PERSONA),--persona "$(PERSONA)")

# Show everything about a contact
# Usage: make show PHONE=33744746977
show:
	@.venv/bin/python scripts/admin.py show --phone "$(PHONE)"

# List all contacts
contacts:
	@.venv/bin/python scripts/admin.py contacts

# Show Ghost's recent thoughts/scratchpad (all contacts or one)
# Usage: make thoughts
# Usage: make thoughts PHONE=33744746977 N=10
thoughts:
	@.venv/bin/python scripts/admin.py thoughts \
		$(if $(PHONE),--phone "$(PHONE)") \
		$(if $(N),--n "$(N)")

# Show conversation history with a contact
# Usage: make convo PHONE=33744746977
# Usage: make convo PHONE=33744746977 N=50
convo:
	@.venv/bin/python scripts/admin.py convo --phone "$(PHONE)" \
		$(if $(N),--n "$(N)")

# Manually send a WhatsApp message as Ghost (logged to DB)
# Usage: make send PHONE=33744746977 TEXT="yo"
# Usage: make send PHONE=33744746977 TEXT="yo\nca va ?"
send:
	@.venv/bin/python scripts/admin.py send --phone "$(PHONE)" --text "$(TEXT)"

# Send a proactive check-in to one or more contacts (runs locally, invokes whatsapp-sender)
# Usage: make proactive PHONES=33652469989,33664970571
# Usage: make proactive PHONES=33652469989 DRY_RUN=1
proactive:
	@.venv/bin/python scripts/admin.py proactive \
		--phones "$(PHONES)" \
		$(if $(DRY_RUN),--dry-run)

# Show or update Ghost's persistent mood state
# Usage: make mood
# Usage: make mood NOTES="bad week" AVAILABILITY=light ENERGY=0.4
# Usage: make mood RESET=1
mood:
	@.venv/bin/python scripts/admin.py mood \
		$(if $(NOTES),--notes "$(NOTES)") \
		$(if $(AVAILABILITY),--availability "$(AVAILABILITY)") \
		$(if $(ENERGY),--energy "$(ENERGY)") \
		$(if $(RESET),--reset)

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

# Install dashboard npm dependencies
dashboard-install:
	cd dashboard && npm install

# Start the Next.js dashboard dev server
dashboard:
	@cd dashboard && \
	DATABASE_URL=$$(aws ssm get-parameter \
		--name /ghost/$(ENV)/db/connection_string \
		--with-decryption --query Parameter.Value \
		--output text --region $(REGION)) \
	OUTBOUND_QUEUE_URL=$$(aws cloudformation describe-stacks \
		--stack-name ghost-$(ENV) --region $(REGION) \
		--query "Stacks[0].Outputs[?OutputKey=='OutboundQueueUrl'].OutputValue" \
		--output text) \
	AWS_REGION=$(REGION) \
	ENV=$(ENV) \
	npm run dev

# Run evals (all skipped until harness is wired up)
test:
	$(PYTHON) -m unittest discover -s tests/evals -p 'test_*.py' -v

# Live DB connectivity check (requires AWS credentials + dev SSM access)
db-test:
	$(PYTHON) tests/test_db_connectivity.py
