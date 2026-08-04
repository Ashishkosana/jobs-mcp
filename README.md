# jobs-mcp

**An MCP server that gives any LLM live access to US software-engineering job openings.**

Point Claude (or any [Model Context Protocol](https://modelcontextprotocol.io) client)
at this server and it can search current postings — pulled live from company ATS
boards (Greenhouse / Lever / Ashby) and a community new-grad feed — right inside your
conversation. US-only, security-clearance / citizenship-required roles filtered out,
newest first. **No API keys**: every source is a public endpoint.

```
Claude  ──calls──▶  jobs-mcp
                     • search_jobs(query, location, limit)
                     • list_sources()
                       └─▶ Greenhouse · Lever · Ashby · SimplifyJobs feed
                       └─▶ US-only · clearance/citizenship roles excluded · deduped
```

## Tools

| Tool | What it does |
|---|---|
| `search_jobs(query, location, limit)` | Live search; `query` words must all appear in the title (e.g. `"backend engineer"`, `"new grad software engineer"`), `location` is `"us"` or a city/state substring. Returns `{company, title, location, url, posted, source}`. |
| `list_sources()` | The ATS boards + community feed this server pulls from. |

## Install & connect to Claude Code

```bash
git clone https://github.com/Ashishkosana/jobs-mcp && cd jobs-mcp
python3 -m venv .venv && .venv/bin/pip install -e .

# register it (stdio transport):
claude mcp add jobs -- "$(pwd)/.venv/bin/python" -m jobs_mcp
```

Then just ask Claude things like *"find me fresh backend software engineer roles in New York"*
— it calls `search_jobs` and answers from live data.

Works with any MCP client (Claude Desktop, etc.) — point it at
`python -m jobs_mcp` over stdio.

## How it works

An MCP server exposes **tools** a client can discover and call. Here each tool is a
plain Python function decorated with `@server.tool()`; its type hints become the input
schema the model sees. On a call, the server fetches every source concurrently (a dead
board is skipped, not fatal), applies the US + clearance filters, dedupes, and returns
structured rows. See `src/jobs_mcp/server.py`.

## Scope / honesty

- Sources are a curated company list + one community feed, not "every job on the
  internet" — LinkedIn/Indeed block scraping, so this uses public ATS APIs instead.
- The clearance filter is lexical (keywords + known defense employers); it catches the
  common cases, not every phrasing.

## License

MIT
