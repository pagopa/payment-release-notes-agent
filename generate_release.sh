#!/usr/bin/env bash
set -euo pipefail

# Usage: ./generate_release.sh <platform> <pr_number> [version] [jira_issue_key] [output.pdf]
#
# Positional arguments:
#   platform        GitHub owner/repo (e.g. pagopa/pagopa-infra)
#   pr_number       Pull Request number
#   version         Release version (default: 1.0.0)
#   jira_issue_key  JIRA ticket key (e.g. PROJ-123) — optional
#   output.pdf      Output file name (default: release_notes_<pr>.pdf)
#
# Environment variables:
#   BASE_URL             App Service base URL
#                        (default: https://release-notes-agent-dwhhfya4cyh7hqap.italynorth-01.azurewebsites.net)
#   API_KEY              Optional API key sent as x-api-key header (e.g. APIM subscription key)
#   CONFLUENCE_SPACE     Confluence space key (e.g. PAYMCLOUD)
#   CONFLUENCE_PARENT    Title or numeric ID of the parent page
#   CONFLUENCE_TITLE     Title of the Confluence page to create
#
# Examples:
#   # PDF only
#   ./generate_release.sh pagopa/pagopa-infra 3922 1.2.0
#
#   # PDF + JIRA attachment
#   ./generate_release.sh pagopa/pagopa-infra 3922 1.2.0 PROJ-123
#
#   # PDF + JIRA + Confluence page
#   CONFLUENCE_SPACE=PAYMCLOUD \
#   CONFLUENCE_PARENT=1590690001 \
#   CONFLUENCE_TITLE="Deploy pagopa-infra v1.2.0" \
#   ./generate_release.sh pagopa/pagopa-infra 3922 1.2.0 PROJ-123
#
#   # With API key (e.g. APIM subscription key)
#   API_KEY=xxx ./generate_release.sh pagopa/pagopa-infra 3922 1.2.0

BASE_URL="${BASE_URL:-https://pagopa-d-itn-rn-agent-app.azurewebsites.net}"
API_KEY="${API_KEY:-}"

PLATFORM="${1:-}"
PR_NUMBER="${2:-}"
VERSION="${3:-1.0.0}"
JIRA_ISSUE_KEY="${4:-}"
OUTPUT="${5:-release_notes_${PR_NUMBER}.pdf}"

CONFLUENCE_SPACE="${CONFLUENCE_SPACE:-}"
CONFLUENCE_PARENT="${CONFLUENCE_PARENT:-}"
CONFLUENCE_TITLE="${CONFLUENCE_TITLE:-}"

POLL_INTERVAL=15  # seconds between each status poll
MAX_WAIT=900      # maximum wait time in seconds (15 min)

# ── Validation ────────────────────────────────────────────────────────────────

if [[ -z "$PLATFORM" || -z "$PR_NUMBER" ]]; then
  echo "Usage: $0 <platform> <pr_number> [version] [jira_issue_key] [output.pdf]"
  echo ""
  echo "Arguments:"
  echo "  platform        GitHub owner/repo (e.g. pagopa/pagopa-infra)"
  echo "  pr_number       Pull Request number"
  echo "  version         Release version (default: 1.0.0)"
  echo "  jira_issue_key  JIRA ticket key (e.g. PROJ-123) — optional"
  echo "  output.pdf      Output file (default: release_notes_<pr>.pdf)"
  echo ""
  echo "Environment variables:"
  echo "  BASE_URL              App Service base URL"
  echo "  API_KEY               Optional API key (x-api-key header)"
  echo "  CONFLUENCE_SPACE      Confluence space key (e.g. PAYMCLOUD)"
  echo "  CONFLUENCE_PARENT     Title or numeric ID of the parent page"
  echo "  CONFLUENCE_TITLE      Title of the Confluence page to create"
  echo ""
  echo "Examples:"
  echo "  $0 pagopa/pagopa-infra 3922 1.2.0"
  echo "  $0 pagopa/pagopa-infra 3922 1.2.0 PROJ-123"
  echo "  CONFLUENCE_SPACE=PAYMCLOUD CONFLUENCE_PARENT=1590690001 \\"
  echo "    CONFLUENCE_TITLE='Deploy v1.2.0' $0 pagopa/pagopa-infra 3922 1.2.0 PROJ-123"
  exit 1
fi

AUTH_HEADER=""
if [[ -n "$API_KEY" ]]; then
  AUTH_HEADER="-H \"x-api-key: ${API_KEY}\""
fi

# ── 1. Start job ──────────────────────────────────────────────────────────────

echo "→ Starting generation: ${PLATFORM} PR#${PR_NUMBER} v${VERSION}${JIRA_ISSUE_KEY:+ → JIRA ${JIRA_ISSUE_KEY}}"

EXTRA_FIELDS=""
[[ -n "$JIRA_ISSUE_KEY"   ]] && EXTRA_FIELDS+=", \"jira_issue_key\": \"${JIRA_ISSUE_KEY}\""
[[ -n "$CONFLUENCE_SPACE"  ]] && EXTRA_FIELDS+=", \"confluence_space\": \"${CONFLUENCE_SPACE}\""
[[ -n "$CONFLUENCE_PARENT" ]] && EXTRA_FIELDS+=", \"confluence_parent_page\": \"${CONFLUENCE_PARENT}\""
[[ -n "$CONFLUENCE_TITLE"  ]] && EXTRA_FIELDS+=", \"confluence_page_title\": \"${CONFLUENCE_TITLE}\""

CURL_ARGS=(-X POST "${BASE_URL}/api/generate"
  -H "Content-Type: application/json"
  -d "{\"platform\": \"${PLATFORM}\", \"pr_number\": ${PR_NUMBER}, \"version\": \"${VERSION}\"${EXTRA_FIELDS}}")
[[ -n "$API_KEY" ]] && CURL_ARGS+=(-H "x-api-key: ${API_KEY}")

RESPONSE=$(curl "${CURL_ARGS[@]}" 2>/dev/null) || true

echo "  response: $RESPONSE"

if [[ -z "$RESPONSE" ]]; then
  echo "✗ No response from the server. Check BASE_URL."
  exit 1
fi

JOB_ID=$(echo "$RESPONSE" | grep -o '"job_id": *"[^"]*"' | grep -o '"[^"]*"$' | tr -d '"' || true)

if [[ -z "$JOB_ID" ]]; then
  echo "✗ Unexpected response (no job_id): $RESPONSE"
  exit 1
fi

echo "✓ Job started: ${JOB_ID}"

# ── 2. Poll status ────────────────────────────────────────────────────────────

ELAPSED=0
while [[ $ELAPSED -lt $MAX_WAIT ]]; do
  sleep "$POLL_INTERVAL"
  ELAPSED=$((ELAPSED + POLL_INTERVAL))

  STATUS_CURL_ARGS=(-sf "${BASE_URL}/api/status/${JOB_ID}")
  [[ -n "$API_KEY" ]] && STATUS_CURL_ARGS+=(-H "x-api-key: ${API_KEY}")

  STATUS_RESPONSE=$(curl "${STATUS_CURL_ARGS[@]}" || true)
  STATUS=$(echo "$STATUS_RESPONSE" | grep -o '"status": *"[^"]*"' | grep -o '"[^"]*"$' | tr -d '"' || true)

  echo "  [${ELAPSED}s] status: ${STATUS}"

  if [[ "$STATUS" == "completed" ]]; then
    DOWNLOAD_URL=$(echo "$STATUS_RESPONSE" | grep -o '"download_url": *"[^"]*"' | grep -o '"[^"]*"$' | tr -d '"' || true)
    break
  elif [[ "$STATUS" == "failed" ]]; then
    ERROR=$(echo "$STATUS_RESPONSE" | grep -o '"error": *"[^"]*"' | grep -o '"[^"]*"$' | tr -d '"' || true)
    echo "✗ Job failed: ${ERROR}"
    exit 1
  fi
done

if [[ "$STATUS" != "completed" ]]; then
  echo "✗ Timeout after ${MAX_WAIT}s — job is still in status: ${STATUS}"
  exit 1
fi

# ── 3. Download PDF ───────────────────────────────────────────────────────────

echo "→ Downloading PDF..."
curl -sf "$DOWNLOAD_URL" --output "$OUTPUT"
echo "✓ PDF saved: ${OUTPUT}"
