
## 2026-04-17 — Phase 05-02 discovery

- `pipeline_defs/cinematic.yaml` references `web_search` tool in its `research` stage `tools_available` list, but `web_search` is NOT registered in `tools/tool_registry` (not a BaseTool). This is a PRE-EXISTING manifest/registry desync unrelated to Plan 05-02.
- Impact: `validate_synthesized_pipeline(cinematic_manifest)` reports one issue. The validator itself is correct.
- Remediation options (out of scope for 05-02):
  1. Add `web_search` as a BaseTool-subclassed tool (likely a wrapper around existing agent web search capability)
  2. Remove `web_search` from the cinematic research stage and rely on the agent's built-in Web tool outside the pipeline_defs contract
  3. Rename the tools_available list convention to allow "intrinsic" agent capabilities
- Deferred to: v2.1 or whenever the web_search reference is reconciled.
