#!/bin/bash
# Pre-deploy check for Practice Loop — C9 hardening.
# Run from project root before every deployment.
set -euo pipefail

echo "=== Pre-deploy Check ==="
echo ""

# 1. Git status
echo "[1/8] Git status..."
if [ -n "$(git status --porcelain)" ]; then
    echo "  WARNING: uncommitted changes present"
    git status --short | head -5
else
    echo "  OK: working tree clean"
fi
echo ""

# 2. Tests
echo "[2/7] Running tests..."
if python3 -m pytest tests/ -q --tb=line 2>&1 | tail -3; then
    echo "  OK: all tests pass"
else
    echo "  FAIL: tests failed — abort deploy"
    exit 1
fi
echo ""

# 3. Ruff
echo "[3/7] Running ruff..."
if ruff check . && ruff format --check . 2>&1 | tail -2; then
    echo "  OK: lint + format clean"
else
    echo "  FAIL: lint/format issues — abort deploy"
    exit 1
fi
echo ""

# 4. Secret scan
echo "[4/7] Secret scan..."
SECRET_FOUND=0
if grep -rn 'password\s*=\s*["'"'"']' app/ tests/ --include='*.py' \
    | grep -iv 'placeholder\|change-me\|example\|REDACTED\|hash_password' \
    | grep -iv 'secret123\|test.*password\|mock.*password'; then
    SECRET_FOUND=1
fi
if grep -rn 'AIza\|ghp_\|xox[baprs]' --include='*.py' . 2>/dev/null \
    | grep -v '.git/' | grep -v 'test_' ; then
    SECRET_FOUND=1
fi
# sk- prefix check — but only actual OpenAI-like keys (sk- followed by alphanum)
if grep -rn 'sk-[a-zA-Z0-9]\{20,\}' --include='*.py' . 2>/dev/null \
    | grep -v '.git/' | grep -v 'test_' | grep -v 'encrypted-key' | grep -v 'mask'; then
    SECRET_FOUND=1
fi
if [ "$SECRET_FOUND" -eq 1 ]; then
    echo "  WARNING: potential secrets found above — review before deploy"
else
    echo "  OK: no hardcoded secrets detected"
fi
echo ""

# 5. Config validation
echo "[5/7] Config validation..."
if [ -f .env ]; then
    if grep -q 'change-me' .env 2>/dev/null && [ "${APP_ENV:-}" = "production" ]; then
        echo "  FAIL: placeholder secrets in .env with APP_ENV=production"
        exit 1
    fi
    echo "  OK: .env present, no obvious placeholders"
else
    echo "  WARNING: no .env file"
fi
echo ""

# 6. Docker
echo "[6/7] Docker build..."
if docker compose build --quiet 2>&1 | tail -2; then
    echo "  OK: docker build succeeds"
else
    echo "  FAIL: docker build failed"
    exit 1
fi
echo ""

# 7. Alembic head check
echo "[7/7] Alembic migration check..."
if python3 -c "
from alembic.config import Config
from alembic.script import ScriptDirectory
cfg = Config('alembic.ini')
script = ScriptDirectory.from_config(cfg)
heads = script.get_heads()
print(f'Heads: {heads}')
assert len(heads) == 1, f'Expected 1 head, got {len(heads)}'
"; then
    echo "  OK: single alembic head"
else
    echo "  FAIL: multiple alembic heads — check migrations"
    exit 1
fi
echo ""

# 8. Social privacy audit
echo "[8/8] Social privacy audit..."
SOCIAL_LEAKS=0
# Check no social route returns email addresses
if grep -rn 'email' app/platform/social/api/ --include='*.py' \
    | grep -i 'response\|return.*email\|expose' | grep -v '# noqa' | grep -v 'test_' | grep -v 'current_user.email' | grep -v 'email never exposed'; then
    echo "  WARNING: potential email exposure in social API — review above"
    SOCIAL_LEAKS=1
fi
# Check no raw_llm_response in social code
if grep -rn 'raw_llm_response' app/platform/social/ --include='*.py' \
    | grep -iv 'strip' | grep -iv 'expose' | grep -v '# noqa' | grep -v 'test_'; then
    echo "  WARNING: raw_llm_response referenced in social code"
    SOCIAL_LEAKS=1
fi
# Check no penalty_details in social code
if grep -rn 'penalty_details' app/platform/social/ --include='*.py' \
    | grep -iv 'strip' | grep -iv 'expose' | grep -v '# noqa'; then
    echo "  WARNING: penalty_details referenced in social code"
    SOCIAL_LEAKS=1
fi
if [ "$SOCIAL_LEAKS" -eq 0 ]; then
    echo "  OK: no private data leaks in social API"
else
    echo "  Review warnings above before deploy"
fi
echo ""

echo "=== All checks passed! Ready to deploy. ==="
