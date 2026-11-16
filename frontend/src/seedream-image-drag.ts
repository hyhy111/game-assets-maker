export const SEEDREAM_IMAGE_DRAG_TYPE = 'application/x-gam-seedream-image';
const IMAGE_DRAG_TEXT_PREFIX = 'gam-seedream-image:';
const SOURCE_IMAGE_DRAG_TYPE = 'application/x-gam-source-image';
const SOURCE_IMAGE_TEXT_PREFIX = 'gam-source-image:';
let removeImageDragEffect: (() => void) | undefined;
let currentImageDrag: { absolutePath: string; payload: SeedreamImageDragPayload } | undefined;
let currentSourceImageDrag: { absolutePath: string; id: string } | undefined;

export interface SeedreamImageDragPayload {
  localId: string;
  attemptIndex: number;
}

export function hasImageDrop(dataTransfer: DataTransfer | null): boolean {
  return Boolean(dataTransfer && (hasSeedreamImageDrag(dataTransfer)
    || Array.from(dataTransfer.types).some(type => type === 'Files' || type === SOURCE_IMAGE_DRAG_TYPE)));
}

export type ImageDropResult =
  | { kind: 'candidate'; candidate: SeedreamImageDragPayload }
  | { kind: 'source'; id: string }
  | { kind: 'file'; file: File }
  | { kind: 'error'; key: 'aiCreation.dropSingleImage' | 'aiCreation.dropInvalidImage' };

export function readImageDrop(dataTransfer: DataTransfer | null): ImageDropResult {
  if (dataTransfer && dataTransfer.files.length > 1) {
    return { kind: 'error', key: 'aiCreation.dropSingleImage' };
  }
  const candidate = readSeedreamImageDrag(dataTransfer);
  if (candidate) return { kind: 'candidate', candidate };
  const text = dataTransfer?.getData('text/plain') ?? '';
  // Native WebViews may retain only the plain-text path when the drag re-enters
  // the app; match it back to the in-flight drag like readSeedreamImageDrag does.
  if (currentSourceImageDrag && text === currentSourceImageDrag.absolutePath) {
    return { kind: 'source', id: currentSourceImageDrag.id };
  }
  const id = dataTransfer?.getData(SOURCE_IMAGE_DRAG_TYPE)
    || (text.startsWith(SOURCE_IMAGE_TEXT_PREFIX) ? text.slice(SOURCE_IMAGE_TEXT_PREFIX.length) : '');
  if (/^[a-f0-9]{32}$/.test(id)) return { kind: 'source', id };
  const file = dataTransfer?.files[0];
  if (file && (/^image\/(png|jpeg|webp|bmp|gif|tiff|heic|heif)$/i.test(file.type)
    || (!file.type && /\.(png|jpe?g|webp|bmp|gif|tiff?|heic|heif)$/i.test(file.name)))) {
    return { kind: 'file', file };
  }
  return { kind: 'error', key: 'aiCreation.dropInvalidImage' };
}

export function writeSourceImageDrag(
  dataTransfer: DataTransfer | null,
  id: string,
  source: HTMLElement,
  absolutePath?: string | null,
) {
  if (!dataTransfer) return;
  dataTransfer.effectAllowed = 'copy';
  dataTransfer.setData(SOURCE_IMAGE_DRAG_TYPE, id);
  currentSourceImageDrag = absolutePath ? { absolutePath, id } : undefined;
  // External agent inputs receive a usable local path instead of internal metadata.
  dataTransfer.setData('text/plain', absolutePath || SOURCE_IMAGE_TEXT_PREFIX + id);
  startImageDragEffect(source, dataTransfer);
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
  absolutePath?: string | null,
  preview?: HTMLElement | 'hidden' | null,
) {
  if (!dataTransfer) return;
  dataTransfer.effectAllowed = 'copy';
  const serialized = JSON.stringify(payload);
  dataTransfer.setData(SEEDREAM_IMAGE_DRAG_TYPE, serialized);
  currentImageDrag = absolutePath ? { absolutePath, payload: { ...payload } } : undefined;
  // External agent inputs receive a usable local path instead of internal metadata.
  dataTransfer.setData('text/plain', absolutePath || IMAGE_DRAG_TEXT_PREFIX + serialized);
  if (preview && preview !== 'hidden') {
    try {
      // Reuse the rendered thumbnail so the drag bitmap contains only this image.
      dataTransfer.setDragImage(preview, preview.clientWidth / 2, preview.clientHeight / 2);
    } catch {
      // Preview failures must leave the native drag and its payload usable.
    }
  }
  if (source) startImageDragEffect(source, preview === 'hidden' ? dataTransfer : undefined);
}

function startImageDragEffect(source: HTMLElement, hideNativePreviewFor?: DataTransfer) {
  removeImageDragEffect?.();
  // Avoid Canvas drag bitmaps, which can cancel native WebView drops.
  // The cosmetic overlay never captures input or changes drag/drop acceptance.
  try {
    const document = source.ownerDocument;
    const effect = document.createElement('span');
    const blankPreview = hideNativePreviewFor ? document.createElement('span') : null;
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
      blankPreview?.remove();
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
    if (hideNativePreviewFor && blankPreview) {
      // Keep a transparent snapshot target in the document for the native drag.
      blankPreview.style.cssText = 'position:fixed;left:0;top:0;width:1px;height:1px;opacity:0;pointer-events:none;';
      document.body.appendChild(blankPreview);
      try {
        hideNativePreviewFor.setDragImage(blankPreview, 0, 0);
      } catch {
        blankPreview.remove();
      }
    }
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
      // Native WebViews may retain only text when dragging back into the app.
      if (currentImageDrag && text === currentImageDrag.absolutePath) return { ...currentImageDrag.payload };
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
