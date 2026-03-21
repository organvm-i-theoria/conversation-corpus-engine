# Surface Externalization Plan

## Goal
Expose the conversation corpus engine to Meta and MCP consumers through contract-backed manifests instead of repo-local conventions.

## Steps
1. Add engine-facing and MCP-facing surface export payloads plus a bundle command.
2. Publish schemas for those payloads and register them in the schema catalog.
3. Write exported JSON and markdown artifacts under `reports/surfaces/`.
4. Add regression coverage that seeds a real project state and validates the exported surfaces.
5. Update docs and contributor guidance to reflect the externalization layer.

## Expected Outputs
- `surface_exports.py`
- `cce surface manifest`
- `cce surface context`
- `cce surface bundle`
- Publishable schemas for surface manifest, MCP context, and bundle exports
