export const SEEDREAM_IMAGE_DRAG_TYPE = 'application/x-gam-seedream-image';
const IMAGE_DRAG_TEXT_PREFIX = 'gam-seedream-image:';
let removeImageDragEffect: (() => void) | undefined;

export interface SeedreamImageDragPayload {
  localId: string;
  attemptIndex: number;
}

export function hasImageDrop(dataTransfer: DataTransfer | null): boolean {
  return Boolean(dataTransfer && (hasSeedreamImageDrag(dataTransfer)
    || Array.from(dataTransfer.types).includes('Files')));
}

export type ImageDropResult =
  | { kind: 'candidate'; candidate: SeedreamImageDragPayload }
  | { kind: 'file'; file: File }
  | { kind: 'error'; key: 'aiCreation.dropSingleImage' | 'aiCreation.dropInvalidImage' };

export function readImageDrop(dataTransfer: DataTransfer | null): ImageDropResult {
  if (dataTransfer && dataTransfer.files.length > 1) {
    return { kind: 'error', key: 'aiCreation.dropSingleImage' };
  }
  const candidate = readSeedreamImageDrag(dataTransfer);
  if (candidate) return { kind: 'candidate', candidate };
  const file = dataTransfer?.files[0];
  if (file && (/^image\/(png|jpeg|webp|bmp|gif|tiff|heic|heif)$/i.test(file.type)
    || (!file.type && /\.(png|jpe?g|webp|bmp|gif|tiff?|heic|heif)$/i.test(file.name)))) {
    return { kind: 'file', file };
  }
  return { kind: 'error', key: 'aiCreation.dropInvalidImage' };
}

export function readImageFile(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => typeof reader.result === 'string'
      ? resolve(reader.result) : reject(new Error('Unable to read image'));
    reader.onerror = () => reject(new Error('Unable to read image'));
    reader.onabort = () => reject(new Error('Unable to read image'));
    reader.readAsDataURL(file);
  });
}

export function writeSeedreamImageDrag(
  dataTransfer: DataTransfer | null,
  payload: SeedreamImageDragPayload,
  source?: HTMLElement | null,
) {
  if (!dataTransfer) return;
  dataTransfer.effectAllowed = 'copy';
  const serialized = JSON.stringify(payload);
  dataTransfer.setData(SEEDREAM_IMAGE_DRAG_TYPE, serialized);
  // Native WebView pasteboards also need a standard representation of the drag.
  dataTransfer.setData('text/plain', IMAGE_DRAG_TEXT_PREFIX + serialized);
  if (source) startImageDragEffect(source);
}

function startImageDragEffect(source: HTMLElement) {
  removeImageDragEffect?.();
  // Keep WebView's native drag bitmap: overriding it can cancel the native drop.
  // The cosmetic overlay never captures input or changes drag/drop acceptance.
  try {
    const document = source.ownerDocument;
    const effect = document.createElement('span');
    effect.setAttribute('aria-hidden', 'true');
    effect.textContent = '+';
    effect.style.cssText = 'position:fixed;left:0;top:0;width:28px;height:28px;'
      + 'display:grid;place-items:center;border-radius:50%;border:1px solid #FFBD5C;'
      + 'background:rgba(36,36,36,0.85);color:#FFBD5C;font:20px/1 sans-serif;'
      + 'box-shadow:0 0 14px rgba(255,189,92,0.45);pointer-events:none;'
      + 'user-select:none;visibility:hidden;z-index:2147483647;';
    const move = (event: DragEvent) => {
      effect.style.transform = `translate(${event.clientX + 12}px, ${event.clientY + 12}px)`;
      effect.style.visibility = 'visible';
    };
    const leave = (event: DragEvent) => {
      if (!event.relatedTarget) effect.style.visibility = 'hidden';
    };
    const cleanup = () => {
      effect.remove();
      document.removeEventListener('dragover', move);
      document.removeEventListener('dragleave', leave);
      document.removeEventListener('drop', cleanup, true);
      document.removeEventListener('dragend', cleanup, true);
      removeImageDragEffect = undefined;
    };
    removeImageDragEffect = cleanup;
    document.body.appendChild(effect);
    document.addEventListener('dragover', move);
    document.addEventListener('dragleave', leave);
    document.addEventListener('drop', cleanup, true);
    document.addEventListener('dragend', cleanup, true);
  } catch {
    removeImageDragEffect?.();
    // Cosmetic failures must not interrupt the valid drag payload.
  }
}

export function hasSeedreamImageDrag(dataTransfer: DataTransfer | null): boolean {
  // Protected dragover events expose formats, but not their contents. Validate on drop.
  return Boolean(dataTransfer && Array.from(dataTransfer.types)
    .some(type => type === SEEDREAM_IMAGE_DRAG_TYPE || type === 'text/plain'));
}

export function readSeedreamImageDrag(dataTransfer: DataTransfer | null): SeedreamImageDragPayload | null {
  if (!dataTransfer) return null;
  try {
    let serialized = dataTransfer.getData(SEEDREAM_IMAGE_DRAG_TYPE);
    if (!serialized) {
      const text = dataTransfer.getData('text/plain');
      if (!text.startsWith(IMAGE_DRAG_TEXT_PREFIX)) return null;
      serialized = text.slice(IMAGE_DRAG_TEXT_PREFIX.length);
    }
    const payload = JSON.parse(serialized) as Partial<SeedreamImageDragPayload>;
    if (typeof payload.localId !== 'string' || !payload.localId) return null;
    if (!Number.isInteger(payload.attemptIndex) || Number(payload.attemptIndex) < 0) return null;
    return { localId: payload.localId, attemptIndex: Number(payload.attemptIndex) };
  } catch {
    return null;
  }
}
