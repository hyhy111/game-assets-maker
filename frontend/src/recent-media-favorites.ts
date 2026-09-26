import { ref } from 'vue';

const STORAGE_KEY = 'gam:recent-media-favorites';

export function imageMediaKey(batchId: string, attemptId: string): string {
  return `image:${batchId}:${attemptId}`;
}

export function videoMediaKey(taskId: string): string {
  return `video:${taskId}`;
}

export function useRecentMediaFavorites() {
  const favoriteMediaKeys = ref(loadFavoriteMediaKeys());

  function isFavorite(mediaKey: string): boolean {
    return favoriteMediaKeys.value.has(mediaKey);
  }

  function toggleFavorite(mediaKey: string) {
    const next = new Set(favoriteMediaKeys.value);
    if (next.has(mediaKey)) next.delete(mediaKey);
    else next.add(mediaKey);
    favoriteMediaKeys.value = next;
    saveFavoriteMediaKeys(next);
  }

  return { imageMediaKey, videoMediaKey, isFavorite, toggleFavorite };
}

function loadFavoriteMediaKeys(): Set<string> {
  try {
    if (typeof localStorage === 'undefined') return new Set();
    const value = localStorage.getItem(STORAGE_KEY);
    const parsed = value ? JSON.parse(value) : [];
    return new Set(Array.isArray(parsed) ? parsed.filter((item): item is string => typeof item === 'string') : []);
  } catch {
    return new Set();
  }
}

function saveFavoriteMediaKeys(keys: Set<string>) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify([...keys]));
  } catch {
    // Favorites remain available for this window when storage is unavailable.
  }
}
