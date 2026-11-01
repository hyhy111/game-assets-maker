/** Resolve newly selected folders without changing persisted storage roots. */
export function storageRootForSelection(
  selectedPath: string,
  folder: 'project' | 'cache',
  currentRoot?: string,
): string {
  const windows = /^[a-z]:[\\/]|^\\\\/i.test(selectedPath);
  const trailingSeparators = windows ? /[\\/]+$/ : /\/+$/;
  const root = selectedPath.replace(trailingSeparators, '');
  const comparable = (value: string) => {
    const normalized = value.replace(trailingSeparators, '');
    return windows ? normalized.replace(/\\/g, '/').toLowerCase() : normalized;
  };
  const basename = root.split(windows ? /[\\/]/ : /\//).pop() ?? '';
  if ((currentRoot && comparable(root) === comparable(currentRoot))
    || (windows ? basename.toLowerCase() : basename) === folder) {
    return root || selectedPath;
  }
  const separator = windows && selectedPath.includes('\\') ? '\\' : '/';
  return `${root}${separator}${folder}`;
}
