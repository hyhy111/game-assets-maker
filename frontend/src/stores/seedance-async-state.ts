export type SeedanceAsyncResource =
  | 'settings'
  | 'cache'
  | 'tasks'
  | 'task-detail'
  | 'task-action'
  | 'connection'
  | 'image-selection';

export interface SeedanceOperationTicket {
  resource: SeedanceAsyncResource;
  resourceGeneration: number;
  operationGeneration: number;
}

export class SeedanceAsyncGuard {
  private latestOperationGeneration = 0;
  private readonly resourceGenerations = new Map<SeedanceAsyncResource, number>();

  begin(resource: SeedanceAsyncResource): SeedanceOperationTicket {
    const resourceGeneration = (this.resourceGenerations.get(resource) ?? 0) + 1;
    this.resourceGenerations.set(resource, resourceGeneration);
    this.latestOperationGeneration += 1;
    return { resource, resourceGeneration, operationGeneration: this.latestOperationGeneration };
  }

  isResourceCurrent(ticket: SeedanceOperationTicket): boolean {
    return this.resourceGenerations.get(ticket.resource) === ticket.resourceGeneration;
  }

  isLatestOperation(ticket: SeedanceOperationTicket): boolean {
    return this.latestOperationGeneration === ticket.operationGeneration;
  }
}

type SeedanceTaskIdentity = {
  local_id: string;
  created_at: string;
};

function revisionFor(revisions: ReadonlyMap<string, number>, localId: string): number {
  return revisions.get(localId) ?? 0;
}

/**
 * Keep the selected task coherent with an accepted list reconciliation. A
 * selection changed after the request began remains authoritative even if an
 * old list response does not contain it.
 */
export function reconcileCurrentTask<Task extends SeedanceTaskIdentity>(
  currentTask: Task | null,
  mergedTasks: readonly Task[],
  snapshotRevisions: ReadonlyMap<string, number>,
  currentRevisions: ReadonlyMap<string, number>
): Task | null {
  if (!currentTask) return null;

  const acceptedTask = mergedTasks.find((task) => task.local_id === currentTask.local_id);
  if (acceptedTask) return acceptedTask;

  return revisionFor(currentRevisions, currentTask.local_id) === revisionFor(snapshotRevisions, currentTask.local_id)
    ? null
    : currentTask;
}

/**
 * Reconcile a list response with mutations received after that request began.
 * Unchanged entries accept the snapshot; changed entries keep their local
 * value, while changed tombstones prevent an old snapshot from resurrecting a
 * deleted task.
 */
export function mergeTaskSnapshot<Task extends SeedanceTaskIdentity>(
  snapshot: readonly Task[],
  current: readonly Task[],
  snapshotRevisions: ReadonlyMap<string, number>,
  currentRevisions: ReadonlyMap<string, number>
): Task[] {
  const snapshotById = new Map(snapshot.map((task) => [task.local_id, task]));
  const currentById = new Map(current.map((task) => [task.local_id, task]));
  const merged = new Map<string, Task>();

  for (const task of snapshot) {
    const currentTask = currentById.get(task.local_id);
    if (revisionFor(currentRevisions, task.local_id) === revisionFor(snapshotRevisions, task.local_id)) {
      merged.set(task.local_id, task);
    } else if (currentTask) {
      merged.set(task.local_id, currentTask);
    }
  }

  for (const task of current) {
    if (snapshotById.has(task.local_id)) continue;
    if (revisionFor(currentRevisions, task.local_id) !== revisionFor(snapshotRevisions, task.local_id)) {
      merged.set(task.local_id, task);
    }
  }

  return [...merged.values()].sort((left, right) => {
    if (left.created_at !== right.created_at) return right.created_at.localeCompare(left.created_at);
    return right.local_id.localeCompare(left.local_id);
  });
}
