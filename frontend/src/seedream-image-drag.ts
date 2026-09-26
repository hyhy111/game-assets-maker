export const SEEDREAM_IMAGE_DRAG_TYPE = 'application/x-gam-seedream-image';

export interface SeedreamImageDragPayload {
  localId: string;
  attemptIndex: number;
}

export function writeSeedreamImageDrag(
  dataTransfer: DataTransfer | null,
  payload: SeedreamImageDragPayload,
) {
  if (!dataTransfer) return;
  dataTransfer.effectAllowed = 'copy';
  dataTransfer.setData(SEEDREAM_IMAGE_DRAG_TYPE, JSON.stringify(payload));
}

export function hasSeedreamImageDrag(dataTransfer: DataTransfer | null): boolean {
  return Boolean(dataTransfer && Array.from(dataTransfer.types).includes(SEEDREAM_IMAGE_DRAG_TYPE));
}

export function readSeedreamImageDrag(dataTransfer: DataTransfer | null): SeedreamImageDragPayload | null {
  if (!dataTransfer) return null;
  try {
    const payload = JSON.parse(dataTransfer.getData(SEEDREAM_IMAGE_DRAG_TYPE)) as Partial<SeedreamImageDragPayload>;
    if (typeof payload.localId !== 'string' || !payload.localId) return null;
    if (!Number.isInteger(payload.attemptIndex) || Number(payload.attemptIndex) < 0) return null;
    return { localId: payload.localId, attemptIndex: Number(payload.attemptIndex) };
  } catch {
    return null;
  }
}
