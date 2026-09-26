export function nextFocusIndex(length: number, currentIndex: number, reverse: boolean): number {
  if (length <= 0) return -1;
  return (currentIndex + (reverse ? -1 : 1) + length) % length;
}

export function trapModalTab(event: KeyboardEvent, root: HTMLElement): void {
  if (event.key !== 'Tab') return;
  const focusable = Array.from(root.querySelectorAll<HTMLElement>('button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'));
  const current = focusable.indexOf(document.activeElement as HTMLElement);
  event.preventDefault();
  focusable[nextFocusIndex(focusable.length, current < 0 ? 0 : current, event.shiftKey)]?.focus();
}
