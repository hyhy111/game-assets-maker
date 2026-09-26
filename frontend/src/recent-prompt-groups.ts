export interface PromptedGeneration {
  local_id: string;
  created_at: string;
  request: {
    prompt: string;
  };
}

export interface RecentPromptGroup<T extends PromptedGeneration> {
  key: string;
  prompt: string;
  items: T[];
}

export function normalizeRecentPrompt(prompt: string): string {
  return prompt.trim().replace(/\s+/g, ' ');
}

export function groupRecentByPrompt<T extends PromptedGeneration>(items: T[]): RecentPromptGroup<T>[] {
  const groups = new Map<string, RecentPromptGroup<T>>();
  const sorted = [...items].sort((left, right) => (
    right.created_at.localeCompare(left.created_at) || right.local_id.localeCompare(left.local_id)
  ));

  for (const item of sorted) {
    const prompt = normalizeRecentPrompt(item.request.prompt);
    const key = prompt || `__empty__:${item.local_id}`;
    const existing = groups.get(key);
    if (existing) {
      existing.items.push(item);
    } else {
      groups.set(key, { key, prompt, items: [item] });
    }
  }

  return [...groups.values()];
}

export function listRecentIndividually<T extends PromptedGeneration>(items: T[]): RecentPromptGroup<T>[] {
  return [...items]
    .sort((left, right) => (
      right.created_at.localeCompare(left.created_at) || right.local_id.localeCompare(left.local_id)
    ))
    .map((item) => ({
      key: `__item__:${item.local_id}`,
      prompt: normalizeRecentPrompt(item.request.prompt),
      items: [item],
    }));
}
