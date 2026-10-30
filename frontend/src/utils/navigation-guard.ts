export type NavigationGuard = () => boolean | Promise<boolean>;

// Keep ordinary navigation synchronous; defer it only when a confirmation is needed.
export function createNavigationGuard() {
  let guard: NavigationGuard | null = null;
  function check() {
    return guard?.() ?? true;
  }
  function run(action: () => void) {
    const allowed = check();
    if (typeof allowed === 'boolean') {
      if (allowed) action();
    } else {
      return allowed.then(confirmed => { if (confirmed) action(); });
    }
  }
  return { check, run, set: (value: NavigationGuard | null) => { guard = value; } };
}
