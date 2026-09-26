import { api } from './api';
import { useSeedanceStore } from './stores/seedance';
import type {
  SeedanceCreateRequest,
  SeedanceRemoteStatus,
  SeedanceSettings,
  SeedanceTask,
  SeedanceTaskLoadResult,
  SeedanceTaskListResult,
  SeedanceTaskResult,
} from './types';

type Expect<T extends true> = T;
type Equal<Actual, Expected> =
  (<T>() => T extends Actual ? 1 : 2) extends
  (<T>() => T extends Expected ? 1 : 2)
    ? true
    : false;

type SeedanceApi = typeof api.seedance;
type SeedanceStore = ReturnType<typeof useSeedanceStore>;

export type _CreateTaskIsTyped = Expect<Equal<
  ReturnType<SeedanceApi['createTask']>,
  Promise<SeedanceTaskResult>
>>;
export type _ListTasksIsTyped = Expect<Equal<
  ReturnType<SeedanceApi['listTasks']>,
  Promise<SeedanceTaskListResult>
>>;
export type _LoadTaskExists = Expect<Equal<
  ReturnType<SeedanceStore['loadTask']>,
  Promise<SeedanceTaskLoadResult>
>>;
export type _SettingsLoaderExists = Expect<Equal<
  ReturnType<SeedanceStore['loadSettings']>,
  Promise<boolean>
>>;
export type _SettingsNeverExposeApiKey = Expect<Equal<
  'api_key' extends keyof SeedanceSettings ? false : true,
  true
>>;
export type _CancellingStatusIsSupported = Expect<Equal<
  Extract<SeedanceRemoteStatus, 'cancelling'>,
  'cancelling'
>>;

declare const createRequest: SeedanceCreateRequest;
declare const task: SeedanceTask;

void api.seedance.createTask(createRequest);
void task.sync_status;
void task.updated_at;
void task.retry_of;
