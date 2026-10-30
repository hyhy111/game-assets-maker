/** Fixed-seed color selection and local alpha deletion for the frame editor. */
export interface PixelBuffer {
  width: number;
  height: number;
  data: Uint8ClampedArray;
}

export function selectColorRegion(
  image: PixelBuffer, x: number, y: number, tolerance: number, contiguous = true
): Uint8Array {
  const { width, height, data } = image;
  const selected = new Uint8Array(width * height);
  x = Math.floor(x);
  y = Math.floor(y);
  if (x < 0 || y < 0 || x >= width || y >= height) return selected;
  const seed = (y * width + x) * 4;
  if (!data[seed + 3]) return selected;
  const limit = Math.min(100, Math.max(0, tolerance)) * 255 / 100;
  const matches = (index: number) => {
    const offset = index * 4;
    return data[offset + 3] > 0
      && Math.abs(data[offset] - data[seed]) <= limit
      && Math.abs(data[offset + 1] - data[seed + 1]) <= limit
      && Math.abs(data[offset + 2] - data[seed + 2]) <= limit;
  };
  if (!contiguous) {
    for (let index = 0; index < selected.length; index++) if (matches(index)) selected[index] = 1;
    return selected;
  }
  const visited = new Uint8Array(selected.length);
  const queue = new Int32Array(selected.length);
  let read = 0;
  let write = 0;
  const add = (index: number) => {
    if (visited[index]) return;
    visited[index] = 1;
    if (matches(index)) {
      selected[index] = 1;
      queue[write++] = index;
    }
  };
  add(y * width + x);
  while (read < write) {
    const index = queue[read++];
    const column = index % width;
    if (column > 0) add(index - 1);
    if (column + 1 < width) add(index + 1);
    if (index >= width) add(index - width);
    if (index + width < selected.length) add(index + width);
  }
  return selected;
}

export function selectionBounds(mask: Uint8Array, width: number, height: number, padding = 0) {
  let left = width, top = height, right = -1, bottom = -1;
  for (let index = 0; index < mask.length; index++) {
    if (!mask[index]) continue;
    const x = index % width, y = Math.floor(index / width);
    left = Math.min(left, x); top = Math.min(top, y);
    right = Math.max(right, x); bottom = Math.max(bottom, y);
  }
  if (right < 0) return null;
  const x = Math.max(0, left - padding), y = Math.max(0, top - padding);
  return { x, y, width: Math.min(width, right + padding + 1) - x, height: Math.min(height, bottom + padding + 1) - y };
}

/** Trace every exposed pixel edge, including holes and disconnected islands. */
export function selectionOutline(mask: Uint8Array, width: number, height: number): string {
  if (mask.length !== width * height) throw new Error('Selection dimensions must match the image');
  const stride = width + 1;
  const edges = new Map<number, number[]>();
  const addEdge = (from: number, to: number) => {
    const outgoing = edges.get(from);
    if (outgoing) outgoing.push(to);
    else edges.set(from, [to]);
  };
  for (let index = 0; index < mask.length; index++) {
    if (!mask[index]) continue;
    const x = index % width;
    const y = Math.floor(index / width);
    const topLeft = y * stride + x;
    if (y === 0 || !mask[index - width]) addEdge(topLeft, topLeft + 1);
    if (x === width - 1 || !mask[index + 1]) addEdge(topLeft + 1, topLeft + stride + 1);
    if (y === height - 1 || !mask[index + width]) addEdge(topLeft + stride + 1, topLeft + stride);
    if (x === 0 || !mask[index - 1]) addEdge(topLeft + stride, topLeft);
  }
  const path: string[] = [];
  while (edges.size) {
    const start = edges.keys().next().value!;
    let point = start;
    path.push(`M${point % stride} ${Math.floor(point / stride)}`);
    do {
      const outgoing = edges.get(point)!;
      const next = outgoing.pop()!;
      if (!outgoing.length) edges.delete(point);
      if (next === start) path.push('Z');
      else if (Math.floor(point / stride) === Math.floor(next / stride)) path.push(`H${next % stride}`);
      else path.push(`V${Math.floor(next / stride)}`);
      point = next;
    } while (point !== start);
  }
  return path.join(' ');
}

export function deleteSelection(image: PixelBuffer, selected: Uint8Array, feather: number): Uint8ClampedArray {
  const { width, height, data } = image;
  if (selected.length !== width * height) throw new Error('Selection dimensions must match the image');
  const output = new Uint8ClampedArray(data);
  const radius = Math.min(12, Math.max(0, Math.round(feather)));
  const bounds = selectionBounds(selected, width, height, 1);
  if (!bounds) return output;
  if (!radius) {
    for (let pixel = 0; pixel < selected.length; pixel++) {
      if (selected[pixel]) output.fill(0, pixel * 4, pixel * 4 + 4);
    }
    return output;
  }
  const { x, y, width: bw, height: bh } = bounds;
  // Measure inward from unselected pixels. Image borders are also selection boundaries.
  const distances = new Float32Array(bw * bh);
  for (let row = 0; row < bh; row++) {
    for (let col = 0; col < bw; col++) {
      const index = row * bw + col;
      const px = x + col, py = y + row;
      if (!selected[py * width + px]) continue;
      distances[index] = Math.min(px + 1, width - px, py + 1, height - py);
      if (col) distances[index] = Math.min(distances[index], distances[index - 1] + 1);
      if (row) distances[index] = Math.min(distances[index], distances[index - bw] + 1);
      if (row && col) distances[index] = Math.min(distances[index], distances[index - bw - 1] + Math.SQRT2);
      if (row && col + 1 < bw) distances[index] = Math.min(distances[index], distances[index - bw + 1] + Math.SQRT2);
    }
  }
  for (let row = bh - 1; row >= 0; row--) {
    for (let col = bw - 1; col >= 0; col--) {
      const index = row * bw + col;
      const pixel = (y + row) * width + x + col;
      if (!selected[pixel]) continue;
      if (col + 1 < bw) distances[index] = Math.min(distances[index], distances[index + 1] + 1);
      if (row + 1 < bh) distances[index] = Math.min(distances[index], distances[index + bw] + 1);
      if (row + 1 < bh && col + 1 < bw) distances[index] = Math.min(distances[index], distances[index + bw + 1] + Math.SQRT2);
      if (row + 1 < bh && col) distances[index] = Math.min(distances[index], distances[index + bw - 1] + Math.SQRT2);
      const offset = pixel * 4;
      // The outermost selected 1px is partial; only the selected interior is fully erased.
      const t = Math.min(1, distances[index] / (radius + 1));
      const keep = 1 - t * t * (3 - 2 * t);
      output[offset + 3] = Math.round(data[offset + 3] * keep);
      if (!output[offset + 3]) output.fill(0, offset, offset + 3);
    }
  }
  return output;
}

/** Erase a round stroke segment with an inward soft edge, relative to the stroke's original pixels. */
export function eraseBrushSegment(
  image: PixelBuffer, before: PixelBuffer,
  from: { x: number; y: number }, to: { x: number; y: number },
  diameter: number, feather: number
) {
  const { width, height, data } = image;
  const radius = diameter / 2;
  const softness = Math.max(0, feather);
  const x = Math.max(0, Math.floor(Math.min(from.x, to.x) - radius - 1));
  const y = Math.max(0, Math.floor(Math.min(from.y, to.y) - radius - 1));
  const right = Math.min(width, Math.ceil(Math.max(from.x, to.x) + radius + 1));
  const bottom = Math.min(height, Math.ceil(Math.max(from.y, to.y) + radius + 1));
  const dx = to.x - from.x, dy = to.y - from.y;
  const lengthSquared = dx * dx + dy * dy;
  for (let row = y; row < bottom; row++) {
    for (let col = x; col < right; col++) {
      const along = lengthSquared ? Math.max(0, Math.min(1,
        ((col + 0.5 - from.x) * dx + (row + 0.5 - from.y) * dy) / lengthSquared
      )) : 0;
      const distance = Math.hypot(col + 0.5 - from.x - along * dx, row + 0.5 - from.y - along * dy);
      let keep;
      if (softness) {
        const t = Math.max(0, Math.min(1, (radius - distance) / softness));
        keep = 1 - t * t * (3 - 2 * t);
      } else {
        // Half-pixel coverage preserves antialiasing for hard brushes, including 1px strokes.
        keep = Math.max(0, Math.min(1, distance - radius + 0.5));
      }
      const offset = (row * width + col) * 4;
      // Combining against the stroke baseline avoids event-density-dependent darkening.
      data[offset + 3] = Math.min(data[offset + 3], Math.round(before.data[offset + 3] * keep));
      if (!data[offset + 3]) data.fill(0, offset, offset + 3);
    }
  }
  return { x, y, width: right - x, height: bottom - y };
}
