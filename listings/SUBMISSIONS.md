# Listing the Fragment plugin

Everything below is prepared but **not submitted**. Prerequisites: the repo is public, and the release commit
is tagged (latest: `v0.1.8`; pin the tag you submit).

## Shared copy

- **Name:** Fragment
- **One line:** Build money flows in your app on a ledger that enforces its own rules.
- **Short description (as submitted to Cursor):** Helps coding agents build prepaid credits, wallets, payouts,
  escrow and spending limits on a Fragment ledger. The ledger refuses bad changes itself: balances can't go
  negative and nothing is credited twice, even if the app's code has a bug. Includes tested code in TypeScript,
  Python and Ruby, and six judged recipes. Payments stay on Stripe or your bank; the plugin never moves money.
- **Long description:** Coding agents keep app balances in a `balance` column or a ledger they write
  themselves, so the rules ("never negative", "credit a purchase once") hold only as long as every code path
  is right. This plugin teaches the agent to keep balances in a Fragment ledger, where each entry type
  carries conditions the ledger checks on every post. It includes a fair comparison with a ledger in your own
  database, a tested quickstart (schema and TypeScript, Python, Ruby code), six recipes each built and judged
  (credits, payouts, memberships, spending authority, escrow, lending), a Python kit, and a judge that proves a
  flow by attacking the ledger directly. Payments stay on Stripe or your bank; Fragment records and enforces.
- **Category:** development (fintech, payments where offered)
- **Data disclosure:** the skills and kit run locally. With the optional MCP configured, the agent calls the
  user's own Fragment workspace with the user's authorization. The kit's `FragmentLedger` calls the Fragment
  API with the Fragment CLI's stored credentials. Nothing is sent anywhere else. The plugin never moves money.
- **Support:** help@fragment.dev · **Privacy policy:** https://fragment.dev/legal · **Icon:** `plugins/fragment/.claude-plugin/icon.png` (1024 × 1024, the press-kit square logo, dark)

## Directories

| Directory | Door | Status | To do at submission |
|---|---|---|---|
| Our Claude Code marketplace | `claude plugin marketplace add fragment-dev/fragment-plugins` | Ready; works today on the private repo | Make the repo public |
| skills.sh / `npx skills add fragment-dev/fragment-plugins` | Automatic from the public repo | Ready | Make the repo public |
| Gemini CLI extensions | Daily crawl of public repos with the `gemini-cli-extension` topic | `gemini-extension.json` + `GEMINI.md` added | Add the topic; check with `gemini extensions install <repo>` |
| Anthropic directory (plugin) | claude.ai/directory/manage → Submit new → Plugin bundle → this repo, path `plugins/fragment` | **Submitted 31 Oct** (v0.1.5): scan passed, in review | Answer the data-handling questions with the disclosure above |
| Anthropic directory (MCP connector) | Same portal → MCP connector | **Blocked**: needs one public MCP URL | Fragment eng: a shared MCP endpoint (or confirm per-workspace URLs can't be listed) |
| Official MCP registry | `mcp-publisher init` (to get the current schema), then publish with the fields in [mcp-registry-server.json](mcp-registry-server.json) | **Blocked** on the same URL; DNS TXT on fragment.dev for `dev.fragment/*` | DNS record; fill in the URL |
| Cursor marketplace | cursor.com/marketplace/publish (manual review, ~2 weeks reported) | **Submitted 31 Oct** (publisher application, handle `fragment`, owner Individual · tom@fragment.dev) | Wait for Cursor's review email |
| OpenAI (ChatGPT / Codex plugins) | platform.openai.com/plugins → Create plugin → "Skills only" | Ready as skills only | Identity verification; domain challenge file on fragment.dev |
| Grok Build | PR to xai-org/plugin-marketplace with [grok-marketplace-entry.json](grok-marketplace-entry.json) | Entry drafted | Pin the release SHA; run their `validate-catalog.py` |
| VS Code / Copilot | Via the MCP registry, then partnerships@github.com | Blocked on the MCP URL | — |

**Policy note:** Anthropic's connector review and OpenAI's plugin guidelines both refuse tools that transfer
money. This plugin and Fragment's MCP record and check balances only; say so in every submission.
