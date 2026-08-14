# Browser, accessibility and agent usability testing

PracticeLoop uses the Node.js Playwright stack for deterministic browser testing and agent-led
exploration:

- Playwright Test: Chromium, Firefox, WebKit, desktop/tablet/mobile projects;
- `@axe-core/playwright`: WCAG 2 A/AA and 2.1 A/AA automated checks;
- Playwright MCP: accessibility-tree browser control for an AI agent;
- HTML reports, screenshots, video and trace on failure.

## Installation

Node.js 22+ is required. With nvm:

```bash
source ~/.nvm/nvm.sh
nvm use 22
npm ci
npx playwright install chromium firefox webkit
```

If browser launch reports missing Linux libraries, install them once:

```bash
sudo apt update
sudo apt install -y python3.13-venv
sudo env PATH="$PATH" npx playwright install-deps chromium firefox webkit
```

The `python3.13-venv` package is required only for the legacy Python/pytest Playwright smoke. The
Node.js Playwright Test and MCP stack do not depend on that virtualenv.

## Deterministic tests

Start PracticeLoop on PostgreSQL or SQLite, then run:

```bash
E2E_BASE_URL=http://127.0.0.1:8000 npm run test:browser
npm run test:browser:smoke
npm run test:a11y
npm run test:usability
npm run test:browser:report
```

The suite runs at 1280×800, 768×1024 and 360×800 in Chromium, plus desktop Firefox and WebKit.
Use `npm run browser:doctor` to verify all installed engines can launch.

To test the static Design v2 prototype:

```bash
python3 -m http.server 8090 --directory design
DESIGN_PROTOTYPE_URL=http://127.0.0.1:8090/prototype/ npm run test:browser -- prototype.spec.ts
```

## Interactive agent browser

`.agents/mcp.json` registers the local Playwright MCP server in isolated, headless Firefox mode
(Firefox is available even on a minimal server image). Restart the agent host after installation
so it discovers the server. The same server can be launched manually:

```bash
npm run agent:browser
```

Suggested agent usability prompt:

> Open the portal at http://127.0.0.1:8000. Complete registration, inspect Today, Tasks, Timer,
> Inventory and Social at desktop and 360 px mobile width. Use the accessibility tree and
> screenshots. Report blockers, confusing labels, excessive interaction cost, keyboard traps,
> horizontal overflow, inaccessible controls and deviations from DESIGN_V2.md. Do not mutate
> production data or invoke destructive actions.

## What automated checks cannot prove

Axe and scripted checks cannot establish overall usability, correct information architecture,
appropriate adult tone or whether the task flow feels controlled and comprehensible. Those need
an agent-led walkthrough followed by human review. Automated accessibility results are a floor,
not a WCAG certification.
