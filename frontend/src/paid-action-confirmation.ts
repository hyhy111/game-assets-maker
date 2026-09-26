export type PaidGenerationAction = 'retry' | 'continue';

export async function runConfirmedPaidAction<T>(
  action: PaidGenerationAction | null,
  execute: (action: PaidGenerationAction) => Promise<T>,
): Promise<T | null> {
  if (action === null) return null;
  return execute(action);
}
