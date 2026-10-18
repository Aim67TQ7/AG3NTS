# Operis UI contract

Preserve the approved compact agent representation. Use `web/src/AgentIdentity.tsx` with the capability color from the catalog; use `AgentFlow` for Input → Execute → Output. Keep the same saved name and capability code across library, dashboard, canvas, monitor, history and human review. Never infer a capability from a name or invent a status.

Compact cards show identity, flow symbols and runtime state. Put descriptions, resources, IDs, configuration summaries and repeated warnings in the editor/details. Keep secondary actions in a menu. Do not add visible rows or enlarge cards as incidental polish. Color identifies capability; status is a separate text label. Preserve readable 14px names and 44px interactive targets rather than shrinking text to fit.

For agent presentation changes, build with TypeScript checks and visually verify the authenticated library at desktop and 390px width, plus another agent surface. Check long names, no horizontal page overflow, keyboard access to actions, opening an agent and unchanged held/runtime state. Save screenshots. Preserve workflow records and execution permissions; UI verification must not activate agents.
