# Tripomatic plugins

Connect your AI assistant to your own [Tripomatic](https://tripomatic.com) trips, so it can read and change them with your account.

## Claude Code and Cowork

```
/plugin marketplace add tripomatic/tripomatic_plugins
/plugin install tripomatic@tripomatic_plugins
```

Then sign in to Tripomatic when your assistant asks. The plugin adds three skills:

- `plan-a-trip`: build a trip or add to one.
- `tidy-my-itinerary`: rebalance and reorder a trip.
- `trip-briefing`: the plan, weather, alerts and holidays for a trip.

## ChatGPT and Codex

The same plugin is packaged for OpenAI's plugin directory in the portable Agent Plugins layout: `plugins/tripomatic/plugin.json` (listing and review cases under `extensions.com.openai`), `mcp.json`, the shared `skills/` and `assets/`. Build the upload ZIP with:

```
python3 scripts/build-openai-zip.py
```

It checks the package against OpenAI's submission limits and writes `dist/tripomatic-<version>.zip`. Keep `version` equal in both manifests. Reviewer credentials never go in the package; they are entered in the OpenAI dashboard.

## Any other MCP client

Add this URL as a remote server and sign in: `https://mcp.tripomatic.com/mcp`

Setup steps: <https://tripomatic.com/en/connect-ai>

## Your data

The assistant acts only as you, on your own trips and trips shared with you. You can see and revoke connected assistants in your Tripomatic account. Privacy: <https://tripomatic.com/privacy-policy#ai-assistants>

## Contact

Support: team@tripomatic.com. Security: security@tripomatic.com.
