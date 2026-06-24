#!/bin/bash
# Populate all Ghost dev SSM secrets.
# Run once: bash scripts/setup_ssm.sh
# Requires: aws CLI, profile "default", region eu-west-1

set -e

PROFILE="default"
REGION="eu-west-1"
ENV="dev"

put() {
  aws ssm put-parameter \
    --profile "$PROFILE" \
    --region "$REGION" \
    --name "/ghost/$ENV/$1" \
    --value "$2" \
    --type SecureString \
    --overwrite \
    --output text --query "Version" > /dev/null
  echo "  set /ghost/$ENV/$1"
}

echo ""
echo "Ghost SSM setup — env=$ENV region=$REGION"
echo "------------------------------------------"

# DB — format: postgresql://user:password@host:5432/dbname
read -rsp "DB connection string (postgresql://...): " DB_CONN; echo
put "db/connection_string" "$DB_CONN"

# Anthropic
read -rsp "Anthropic API key: " ANTHROPIC_KEY; echo
put "anthropic/api_key" "$ANTHROPIC_KEY"

# Voyage AI
read -rsp "Voyage AI API key: " VOYAGE_KEY; echo
put "voyage/api_key" "$VOYAGE_KEY"

# WhatsApp
read -rsp "WhatsApp Business API token: " WA_TOKEN; echo
put "whatsapp/api_token" "$WA_TOKEN"

read -rsp "WhatsApp phone number ID: " WA_PHONE_ID; echo
put "whatsapp/phone_number_id" "$WA_PHONE_ID"

read -rsp "WhatsApp webhook verify token (you choose): " WA_VERIFY; echo
put "whatsapp/verify_token" "$WA_VERIFY"

# Telegram
read -rsp "Telegram bot token: " TG_TOKEN; echo
put "telegram/bot_token" "$TG_TOKEN"

echo ""
echo "All secrets stored. Run migrations next:"
echo "  export DATABASE_URL=\$(aws ssm get-parameter --name /ghost/dev/db/connection_string --with-decryption --query Parameter.Value --output text --profile default --region eu-west-1)"
echo "  make migrate"
