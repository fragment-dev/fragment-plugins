// Our platform holds money for recipients and pays them out. Today balances live in memory and nothing
// stops a payout from overdrawing a wallet.
type Rail = 'ach' | 'push_to_card';

export async function payout(recipientId: string, amountCents: number, rail: Rail): Promise<{ ok: boolean }> {
  // ... sends the money through the payment provider
  return { ok: true };
}
