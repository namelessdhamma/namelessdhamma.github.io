# ND MCP Connection Research — Last30Days Delta

Date: 2026-09-10
Status: research input incorporated; not Architecture Control adoption
Branch: `notebooklm-remote-mcp`

## Purpose

Capture recent direct-integration findings discovered through the Last30Days freshness-oriented research capability and translate them into concrete implementation consequences for ND.

Last30Days is treated as a discovery layer only. Important claims are confirmed against primary OpenAI documentation, official repositories, live MCP probes, or actual account/runtime behavior before architecture adoption.

## Confirmed recent platform changes relevant to ND

### 1. Remote MCP and Secure MCP Tunnel are distinct deployment modes

Current OpenAI documentation states that ChatGPT connects to remote MCP servers directly. Local/private/on-prem/developer-machine MCP servers are not directly reachable and should use Secure MCP Tunnel.

Implication:
- public remote Streamable HTTP MCP remains the preferred primary architecture for NotebookLM;
- Secure MCP Tunnel remains a fallback for services that must remain private/local;
- do not reintroduce tunnel-client into NotebookLM primary path once remote MCP is qualified.

This matches the live ND result already obtained: ChatGPT successfully reached the Vercel remote MCP endpoint without Android, Cloud Shell, or Secure MCP Tunnel.

### 2. Search/fetch tools are no longer mandatory

Current OpenAI developer-mode MCP documentation explicitly says search and fetch tools are not required.

Implication:
- ND should prefer narrow semantic MCP surfaces rather than generic search/fetch facades;
- NotebookLM MCP can expose only capabilities such as `list_notebooks`, `create_notebook`, `query_notebook`, `add_source`, etc.;
- future Claude gateway can expose semantic delegation tools such as `delegate_task_to_claude`, `request_claude_critique`, and `request_claude_falsification`;
- avoid a monolithic "ND everything MCP" unless later evidence requires it.

### 3. GitHub plugin marketplaces can distribute OpenAI/Claude-compatible plugin packages

Current OpenAI documentation confirms workspace admins can import plugin marketplaces from public or private GitHub repositories, with daily sync. Supported formats include Codex marketplace manifests and Claude-compatible marketplace/plugin manifests.

Implication:
- GitHub can become a version-controlled capability distribution source for OpenAI/ChatGPT/Codex and Claude-compatible packaging;
- this is a packaging/distribution layer, not a runtime communication channel;
- it must not be confused with GPT <-> Claude bidirectional task transfer.

### 4. Work supports event-triggered tasks for selected connected systems

Current OpenAI documentation confirms event-triggered Work tasks for supported Gmail, Slack, and GitHub events on eligible plans.

Implication:
- ND routing should not assume every external event needs n8n;
- use native ChatGPT event triggers first where supported and sufficient;
- retain n8n for unsupported event sources, durable orchestration, retries, stateful workflows, branching, or cross-system coordination.

## Revised direct-integration routing hierarchy

```text
1. native ChatGPT capability/event trigger
2. direct remote MCP or official API
3. Secure MCP Tunnel for private/local MCP where remote exposure is undesirable
4. webhook/event bridge when direct native trigger is insufficient
5. n8n for durable orchestration/retries/state/unsupported connectors
6. browser/computer-use fallback only where direct interfaces are unavailable
```

Selection should be capability-driven, not provider-name-driven.

## Current NotebookLM consequence

No architecture reversal is justified.

The current primary implementation remains:

```text
ChatGPT
-> remote Streamable HTTP MCP
-> Vercel on-demand runtime
-> narrow NotebookLM adapter
-> consumer NotebookLM
```

Secure MCP Tunnel is retained only as a legacy/private fallback topology.

The Last30Days findings strengthen the current design in three ways:
- narrow semantic tool surface is now explicitly supported by current OpenAI MCP behavior;
- remote MCP is a first-class direct connection and does not require Secure MCP Tunnel;
- GitHub can later distribute the capability package separately from the runtime.

## GPT <-> Claude research consequence

Preferred first proof remains:

```text
GPT
-> narrow remote MCP tool
-> Claude gateway
-> Claude API or Claude Agent SDK
-> structured result
-> MCP
-> GPT
```

Do not create a full multi-agent platform for the first proof.

Minimum delegation envelope for future qualification:
- task
- objective
- relevant context
- authority level
- expected output
- allowed tools
- budget/limits
- independence requirement
- provenance requirement
- return mode
- resumability identifier

Candidate modes:
- EXECUTE
- INDEPENDENT_SOLVE
- CRITIQUE
- FALSIFY
- REVIEW
- CONTINUE

Reverse initiation (Claude -> GPT without human mediation) remains a separate mandatory research gate and should compare webhook/event bus/queue/native trigger/n8n/GitHub-event/direct API mechanisms rather than assuming MCP itself provides callback semantics.

## Governance

MCP remains transport/capability boundary only.

Do not let MCP research create:
- competing StateHead;
- competing Capability Registry;
- second architecture authority;
- monolithic integration layer without demonstrated need.

Authority remains:

```text
fresh StateHead -> exact bound Registry -> active bindings -> durable state
```

## Verification references

Primary OpenAI documentation checked 2026-09-10:
- Developer mode and MCP apps in ChatGPT: https://help.openai.com/en/articles/12584461
- Importing and syncing plugin marketplaces from GitHub: https://help.openai.com/en/articles/20001504
- Plugins in ChatGPT and Codex: https://help.openai.com/en/articles/20001256
- ChatGPT Work and Codex event-triggered tasks: https://help.openai.com/en/articles/20001275

## Tool status note

The exact `Last30Days / last30days-skill` package did not surface in the current ChatGPT Plugin Directory search available to this chat. Therefore it should currently be treated as a separately supplied/installed freshness skill in the ND Automation Agent context rather than assumed to be a globally invokable connector here.
