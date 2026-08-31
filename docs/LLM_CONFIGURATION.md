# LLM configuration

Practice Loop supports two provider scopes and two capabilities.

## Scopes

- **Portal provider** — deployment-managed provider metadata and optional credentials from `.env`. It is visible to users as a shared option and is not editable through the user UI.
- **Personal provider** — user-owned BYOK configuration. The API key is encrypted in the database and is never exposed to another user or to the portal catalog.

A portal provider is used only when the user explicitly selects portal mode/capability. For that explicit portal selection, the runtime resolver may use the deployment-managed key from `PORTAL_LLM_PROVIDERS_JSON`; it never exposes that key to the user or uses it for another user's personal configuration. A database-backed global provider still requires a matching personal BYOK credential.

## Capabilities

Selections are stored independently for:

- `text` — generation, planning, insights, and text-oriented assistants;
- `vision` — image verification and image processing.

The user selects the provider and model in `/llm-configs/`. Models from a database-backed portal provider are limited to enabled catalog entries; personal models are fetched from that user's provider `models.list()` endpoint. Text and vision selections are independent, so chat can use provider A while image processing uses provider B.

## Section policy

Personal BYOK access is disabled by default. Configure allowed product sections with `PERSONAL_LLM_SECTIONS_JSON`, for example:

```dotenv
PERSONAL_LLM_SECTIONS_JSON='["tasks","training","insights"]'
```

Sections not listed in this policy must use portal providers. The settings page shows the policy state and warns that portal usage may be billable.

## Portal providers in `.env`

Set `PORTAL_LLM_PROVIDERS_JSON` to a JSON array. Do not commit real keys:

```dotenv
PORTAL_LLM_PROVIDERS_JSON='[
  {"name":"Portal OpenAI","base_url":"https://api.openai.com/v1","api_key":"replace-me","models":[
    {"name":"gpt-4o-mini","vision":true},
    {"name":"gpt-4o","vision":true}
  ],"supports_text":true}
]'
```

For Docker Compose, the variable is passed through to the app container. Restart the app after changing it. The UI exposes only provider names and model metadata; API keys are never rendered.

For production, prefer an environment/secrets manager rather than a plain `.env` file, restrict file permissions, and rotate any key that was accidentally exposed.
