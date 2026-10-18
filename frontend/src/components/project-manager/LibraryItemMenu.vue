<template>
  <div
    ref="anchor"
    class="inline-flex flex-none"
    :data-item-menu="menuKey"
    @click.stop
    @keydown.stop
  >
    <Menu
      v-slot="{ close }"
      as="div"
    >
      <MenuButton
        type="button"
        class="rounded-md p-1.5 text-gray-500 transition-colors hover:bg-white/5 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
        :aria-label="label"
        :title="label"
        @click="prepareMenu(close)"
        @keydown="prepareMenu(close)"
      >
        <MoreVertical class="h-4 w-4" />
      </MenuButton>
      <Teleport to="body">
        <MenuItems
          class="fixed z-[60] w-36 rounded-lg border border-dark-border bg-dark-surface py-1 shadow-lg focus:outline-none"
          :style="position"
          @click.stop
          @keydown.stop
        >
          <MenuItem v-slot="{ active }">
            <button
              type="button"
              :class="[
                'flex w-full items-center gap-2 rounded px-3 py-2 text-sm transition-colors',
                active ? 'bg-dark-border text-white' : 'text-gray-300',
              ]"
              @click="emit('rename', anchor?.querySelector('button') ?? undefined)"
            >
              <Pencil class="h-4 w-4" />
              {{ t('projectManager.rename') }}
            </button>
          </MenuItem>
        </MenuItems>
      </Teleport>
    </Menu>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { Menu, MenuButton, MenuItem, MenuItems } from '@headlessui/vue';
import { MoreVertical, Pencil } from 'lucide-vue-next';

defineProps<{ menuKey: string; label: string }>();
const emit = defineEmits<{ (event: 'rename', trigger?: HTMLButtonElement): void }>();
const { t } = useI18n();
const anchor = ref<HTMLElement | null>(null);
const position = ref({ top: '0px', left: '0px' });
let closeMenu: (() => void) | undefined;

function prepareMenu(close: () => void) {
  closeMenu = close;
  const rect = anchor.value?.getBoundingClientRect();
  if (!rect) return;
  const top = rect.bottom + 8 + 48 <= window.innerHeight ? rect.bottom + 8 : rect.top - 56;
  position.value = {
    top: `${Math.max(8, top)}px`,
    left: `${Math.max(8, Math.min(rect.right - 144, window.innerWidth - 152))}px`,
  };
}

function closeOnMove() {
  closeMenu?.();
}

onMounted(() => {
  window.addEventListener('scroll', closeOnMove, true);
  window.addEventListener('resize', closeOnMove);
});
onBeforeUnmount(() => {
  window.removeEventListener('scroll', closeOnMove, true);
  window.removeEventListener('resize', closeOnMove);
});
</script>
