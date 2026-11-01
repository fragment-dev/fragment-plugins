// Our AI agents call paid tools on behalf of teams. Today nothing limits what they spend.
type ToolCall = { teamId: string; agentId: string; tool: string; costCents: number };

export async function callTool(call: ToolCall): Promise<{ ok: boolean }> {
  // ... calls the vendor and pays costCents
  return { ok: true };
}
