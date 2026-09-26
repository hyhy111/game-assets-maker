<template>
  <section
    class="project-manager-hero relative overflow-hidden border-b border-dark-border"
    data-test="project-manager-hero"
  >
    <div class="relative mx-auto flex max-w-[1320px] flex-col items-center gap-10 px-4 py-14 sm:px-6 lg:flex-row lg:py-20">
      <div class="flex-1 text-center lg:text-left">
        <h1 class="text-4xl font-bold leading-[1.1] tracking-tight text-white sm:text-5xl lg:text-6xl">
          Prompt →<br>
          <span class="text-primary">Game Assets</span>
        </h1>
        <p class="mx-auto mt-5 max-w-xl text-base leading-relaxed text-gray-400 lg:mx-0 lg:text-lg">
          {{ t('projectManager.heroSubtitle') }}
        </p>

        <div class="mt-8 flex justify-center lg:justify-start">
          <Button
            size="lg"
            class="w-full gap-2 rounded-xl px-7 py-3.5 shadow-xl shadow-primary/20 sm:w-auto"
            data-test="project-manager-hero-start"
            @click="emit('start-ai-creation')"
          >
            <Sparkles class="h-5 w-5" />
            {{ t('projectManager.heroStart') }}
          </Button>
        </div>

        <div class="mt-10 flex flex-wrap items-center justify-center gap-x-6 gap-y-3 text-xs text-gray-500 lg:justify-start">
          <span
            v-for="capability in capabilities"
            :key="capability.label"
            class="flex items-center gap-1.5"
          >
            <span
              class="h-2 w-2 rounded-sm"
              :class="capability.color"
            />
            {{ capability.label }}
          </span>
        </div>
      </div>

      <div class="flex w-full flex-1 items-center justify-center lg:justify-end">
        <div
          class="creation-flow"
          :aria-label="t('projectManager.heroFlowLabel')"
          aria-live="off"
        >
          <svg
            width="0"
            height="0"
            class="absolute"
            aria-hidden="true"
          >
            <defs>
              <symbol
                id="projectHeroKnight"
                viewBox="0 0 120 150"
              >
                <ellipse
                  cx="61"
                  cy="139"
                  rx="34"
                  ry="7"
                  fill="#090909"
                  opacity=".35"
                />
                <path
                  d="M37 67c-8 12-10 34-7 52l23-8 4-42-20-2Z"
                  fill="#6b3f70"
                />
                <path
                  d="M50 104h16l-3 29H49l1-29Zm23 0h14l7 27H80l-7-27Z"
                  fill="#384a65"
                />
                <path
                  d="M45 130h21v10H39c0-5 2-8 6-10Zm35-1h16l8 11H79l1-11Z"
                  fill="#222b3a"
                />
                <path
                  d="M43 61h44l8 47H38l5-47Z"
                  fill="#FFBD5C"
                />
                <path
                  d="m44 71 43-4 4 16-49 5 2-17Z"
                  fill="#FFC15F"
                  opacity=".45"
                />
                <path
                  d="M38 64 25 85l10 9 15-18-12-12Zm50-1 15 18-10 10-16-16 11-12Z"
                  fill="#d59a73"
                />
                <circle
                  cx="66"
                  cy="44"
                  r="20"
                  fill="#d9a17d"
                />
                <path
                  d="M43 43c2-23 15-31 28-29 13 2 20 12 19 29L75 32 43 43Z"
                  fill="#293d5b"
                />
                <path
                  d="M43 42h48v9H43z"
                  fill="#486892"
                />
                <path
                  d="M54 46h25v6H54z"
                  fill="#152034"
                />
                <path
                  d="m97 72 6-4 13 48-7 2-12-46Z"
                  fill="#bdc7d4"
                />
                <path
                  d="m99 70 7-2 3 10-8 2z"
                  fill="#8b5d3e"
                />
                <path
                  d="m108 116 9-2 2 6-11 3z"
                  fill="#d9e1e8"
                />
              </symbol>
            </defs>
          </svg>

          <div class="flow-topline">
            <span class="flow-live">Asset pipeline</span>
            <span>{{ flowCounter }}</span>
          </div>

          <Transition
            name="flow-stage"
            mode="out-in"
          >
            <div
              :key="activeStage"
              class="flow-stage"
            >
              <div
                v-if="activeStage === 0"
                class="flow-card prompt-card"
              >
                <div class="prompt-label">
                  Prompt
                </div>
                <div class="prompt-input">
                  {{ t('projectManager.heroPrompt') }}<span class="prompt-caret" />
                </div>
                <div class="prompt-submit">
                  <span>Seedream · 2K</span>
                  <span>{{ t('projectManager.heroGenerateImage') }}</span>
                </div>
              </div>

              <div
                v-else-if="activeStage === 1"
                class="art-board"
              >
                <svg
                  class="hero-sprite"
                  viewBox="0 0 120 150"
                  aria-hidden="true"
                >
                  <use href="#projectHeroKnight" />
                </svg>
              </div>

              <div
                v-else-if="activeStage === 2"
                class="flow-card combo-card"
              >
                <div class="combo-image">
                  <svg
                    class="hero-sprite"
                    viewBox="0 0 120 150"
                    aria-hidden="true"
                  >
                    <use href="#projectHeroKnight" />
                  </svg>
                </div>
                <div class="combo-copy">
                  <span class="combo-chip">PIC + PROMPT</span>
                  <strong>{{ t('projectManager.heroMotionPrompt') }}</strong>
                  <p>{{ t('projectManager.heroMotionConstraints') }}</p>
                  <span
                    class="combo-wave"
                    aria-hidden="true"
                  >
                    <i
                      v-for="wave in 12"
                      :key="wave"
                    />
                  </span>
                </div>
              </div>

              <div
                v-else-if="activeStage === 3"
                class="animation-board"
              >
                <div class="animation-main">
                  <svg
                    class="hero-sprite"
                    viewBox="0 0 120 150"
                    aria-hidden="true"
                  >
                    <use href="#projectHeroKnight" />
                  </svg>
                </div>
                <div class="frame-strip">
                  <span
                    v-for="frame in 5"
                    :key="frame"
                    class="mini-frame"
                    :class="{ active: frame === 1 }"
                  >
                    <svg
                      class="hero-sprite"
                      viewBox="0 0 120 150"
                      aria-hidden="true"
                      :style="{ '--offset': `${frameOffsets[frame - 1]}px` }"
                    >
                      <use href="#projectHeroKnight" />
                    </svg>
                  </span>
                </div>
              </div>

              <div
                v-else-if="activeStage === 4"
                class="assets-board"
              >
                <div class="asset-head">
                  <strong>Knight · Game Assets</strong>
                  <span class="asset-ready">READY</span>
                </div>
                <div class="asset-grid">
                  <div
                    v-for="action in assetActions"
                    :key="action"
                    class="asset-tile"
                  >
                    <svg
                      class="hero-sprite"
                      viewBox="0 0 120 150"
                      aria-hidden="true"
                    >
                      <use href="#projectHeroKnight" />
                    </svg>
                    <span>{{ action }}</span>
                  </div>
                </div>
                <div class="asset-meta">
                  <span>TRANSPARENT PNG</span>
                  <span>48 FRAMES</span>
                  <span>OFFSET JSON</span>
                </div>
              </div>
            </div>
          </Transition>

          <div
            class="flow-progress"
            aria-hidden="true"
          >
            <span
              v-for="(label, index) in flowLabels"
              :key="label"
              class="flow-step"
              :class="{ active: activeStage === index }"
            >{{ label }}</span>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import { Sparkles } from 'lucide-vue-next';
import { useI18n } from 'vue-i18n';
import Button from '@/components/common/Button.vue';

const emit = defineEmits<{
  'start-ai-creation': [];
}>();

const { t } = useI18n();
const activeStage = ref(0);
const flowLabels = ['Prompt', 'Pic', 'Pic + Prompt', 'Animation', 'Assets'];
const assetActions = ['Idle', 'Run', 'Attack', 'Hurt'];
const frameOffsets = [0, 2, 5, 8, 3];
let flowTimer: ReturnType<typeof window.setInterval> | undefined;

const capabilities = computed(() => [
  { label: t('projectManager.heroTextToImage'), color: 'bg-primary' },
  { label: t('projectManager.heroImageToVideo'), color: 'bg-warning' },
  { label: t('projectManager.heroTransparentBackground'), color: 'bg-success' },
  { label: t('projectManager.heroFrameExport'), color: 'bg-accent' },
]);

const flowCounter = computed(() => (
  `${String(activeStage.value + 1).padStart(2, '0')} / ${String(flowLabels.length).padStart(2, '0')}`
));

onMounted(() => {
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    activeStage.value = flowLabels.length - 1;
    return;
  }
  flowTimer = window.setInterval(advanceFlow, 2800);
});

onBeforeUnmount(() => {
  if (flowTimer !== undefined) window.clearInterval(flowTimer);
});

function advanceFlow() {
  activeStage.value = (activeStage.value + 1) % flowLabels.length;
}
</script>

<style scoped>
.project-manager-hero {
  background: #171717;
}

.creation-flow {
  position: relative;
  width: min(100%, 560px);
  min-height: 370px;
  overflow: hidden;
  isolation: isolate;
  border: 1px solid #333;
  border-radius: 20px;
  background: linear-gradient(145deg, rgb(36 36 36 / 96%), rgb(24 24 24 / 98%));
  box-shadow: 0 28px 70px -38px rgb(255 189 92 / 60%), inset 0 1px rgb(255 255 255 / 3%);
}

.creation-flow::before {
  position: absolute;
  z-index: -1;
  inset: 0;
  background-image:
    linear-gradient(rgb(255 255 255 / 2.5%) 1px, transparent 1px),
    linear-gradient(90deg, rgb(255 255 255 / 2.5%) 1px, transparent 1px);
  background-size: 24px 24px;
  mask-image: linear-gradient(to bottom, black, transparent 82%);
  opacity: 0.28;
  content: '';
}

.flow-topline {
  position: absolute;
  z-index: 10;
  top: 18px;
  right: 20px;
  left: 20px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: #6b7280;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 10px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.flow-live {
  display: inline-flex;
  align-items: center;
  gap: 7px;
}

.flow-live::before {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #2cc985;
  box-shadow: 0 0 10px rgb(44 201 133 / 65%);
  content: '';
}

.flow-stage {
  position: absolute;
  inset: 52px 24px 72px;
  display: grid;
  place-items: center;
}

.flow-stage-enter-active {
  animation: flow-in 0.72s cubic-bezier(0.2, 0.8, 0.2, 1);
}

.flow-stage-leave-active {
  animation: flow-out 0.46s cubic-bezier(0.4, 0, 1, 1);
}

@keyframes flow-in {
  from { opacity: 0; transform: translateY(18px) scale(0.97); filter: blur(7px); }
  to { opacity: 1; transform: none; filter: blur(0); }
}

@keyframes flow-out {
  from { opacity: 1; transform: none; filter: blur(0); }
  to { opacity: 0; transform: translateY(-13px) scale(1.02); filter: blur(5px); }
}

.flow-card {
  width: min(100%, 420px);
  border: 1px solid #3a3a3a;
  border-radius: 15px;
  background: rgb(26 26 26 / 88%);
  box-shadow: 0 18px 38px rgb(0 0 0 / 28%);
}

.prompt-card { padding: 16px; }
.prompt-label { color: #6b7280; font: 10px ui-monospace, SFMono-Regular, Menlo, monospace; letter-spacing: 0.08em; text-transform: uppercase; }
.prompt-input { min-height: 82px; margin-top: 10px; padding: 13px 14px; border: 1px solid rgb(232 154 45 / 72%); border-radius: 11px; color: #e5e7eb; background: #181818; box-shadow: 0 0 0 1px rgb(255 189 92 / 8%), 0 0 28px rgb(255 189 92 / 22%), inset 0 0 20px rgb(255 189 92 / 5%); font-size: 13px; line-height: 1.65; }
.prompt-caret { display: inline-block; width: 2px; height: 14px; margin-left: 3px; vertical-align: -2px; background: #ffc15f; animation: caret-blink 0.8s steps(1) infinite; }
@keyframes caret-blink { 50% { opacity: 0; } }
.prompt-submit { display: flex; align-items: center; justify-content: space-between; margin-top: 12px; color: #6b7280; font: 10px ui-monospace, SFMono-Regular, Menlo, monospace; }
.prompt-submit span:last-child { padding: 6px 9px; border-radius: 7px; color: #1a1a1a; background: #ffbd5c; }

.art-board {
  position: relative;
  display: grid;
  width: min(100%, 330px);
  aspect-ratio: 4 / 3;
  place-items: center;
  overflow: hidden;
  border: 1px solid #3b3b3b;
  border-radius: 16px;
  background-color: #151515;
  background-image:
    linear-gradient(45deg, #202020 25%, transparent 25%),
    linear-gradient(-45deg, #202020 25%, transparent 25%),
    linear-gradient(45deg, transparent 75%, #202020 75%),
    linear-gradient(-45deg, transparent 75%, #202020 75%);
  background-position: 0 0, 0 10px, 10px -10px, -10px 0;
  background-size: 20px 20px;
  box-shadow: 0 18px 42px rgb(0 0 0 / 30%);
}

.art-board::after {
  position: absolute;
  inset: 0;
  background: linear-gradient(to bottom, transparent 46%, rgb(95 167 223 / 35%) 50%, transparent 54%);
  transform: translateY(-110%);
  animation: scan 2.4s ease-in-out infinite;
  content: '';
}

@keyframes scan {
  0%, 15% { transform: translateY(-110%); }
  75%, 100% { transform: translateY(110%); }
}

.hero-sprite { width: 145px; height: 180px; filter: drop-shadow(0 14px 12px rgb(0 0 0 / 45%)); }
.combo-card { display: grid; grid-template-columns: 138px 1fr; gap: 13px; padding: 13px; }
.combo-image { display: grid; min-height: 168px; place-items: center; overflow: hidden; border-radius: 11px; background: linear-gradient(150deg, rgb(255 189 92 / 17%), rgb(203 63 62 / 12%)), #171717; }
.combo-image .hero-sprite { width: 92px; height: 120px; }
.combo-copy { display: flex; min-width: 0; flex-direction: column; padding: 5px 2px; }
.combo-chip { align-self: flex-start; padding: 4px 7px; border: 1px solid rgb(255 189 92 / 30%); border-radius: 6px; color: #ffc15f; background: rgb(255 189 92 / 8%); font: 9px ui-monospace, SFMono-Regular, Menlo, monospace; }
.combo-copy strong { margin-top: 12px; color: white; font-size: 13px; }
.combo-copy p { margin-top: 7px; color: #9ca3af; font-size: 11px; line-height: 1.55; }
.combo-wave { display: flex; height: 22px; align-items: end; gap: 3px; margin-top: auto; }
.combo-wave i { width: 3px; border-radius: 3px; background: #ffbd5c; animation: wave 1s ease-in-out infinite alternate; }
.combo-wave i:nth-child(2n) { animation-delay: -0.45s; }
.combo-wave i:nth-child(3n) { animation-delay: -0.2s; }
@keyframes wave { from { height: 5px; opacity: 0.35; } to { height: 20px; opacity: 1; } }

.animation-board, .assets-board { width: min(100%, 440px); }
.animation-main { position: relative; display: grid; height: 176px; place-items: center; overflow: hidden; border: 1px solid #393939; border-radius: 14px; background: radial-gradient(circle at 50% 78%, rgb(255 189 92 / 16%), transparent 40%), #171717; }
.animation-main::after { position: absolute; right: 8%; bottom: 22px; left: 8%; height: 1px; background: linear-gradient(90deg, transparent, #414141 18%, #414141 82%, transparent); content: ''; }
.animation-main .hero-sprite { width: 112px; height: 142px; animation: sprite-action 1.45s cubic-bezier(0.45, 0, 0.55, 1) infinite; }
@keyframes sprite-action { 0%, 100% { transform: translateX(-14px) rotate(-2deg); } 45% { transform: translateX(13px) translateY(-7px) rotate(3deg); } 62% { transform: translateX(18px) rotate(5deg); } }
.frame-strip { display: grid; grid-template-columns: repeat(5, 1fr); gap: 7px; margin-top: 9px; }
.mini-frame { position: relative; display: grid; height: 49px; place-items: center; overflow: hidden; border: 1px solid #353535; border-radius: 8px; background: #1c1c1c; }
.mini-frame.active { border-color: #ffbd5c; box-shadow: 0 0 0 1px rgb(255 189 92 / 25%); }
.mini-frame .hero-sprite { width: 31px; height: 40px; transform: translateX(var(--offset, 0)); }

.asset-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
.asset-head strong { color: white; font-size: 14px; }
.asset-ready { display: inline-flex; align-items: center; gap: 6px; color: #2cc985; font: 9px ui-monospace, SFMono-Regular, Menlo, monospace; letter-spacing: 0.08em; }
.asset-ready::before { width: 6px; height: 6px; border-radius: 50%; background: currentColor; box-shadow: 0 0 9px currentColor; content: ''; }
.asset-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; }
.asset-tile { display: grid; justify-items: center; gap: 5px; padding: 9px 5px 7px; border: 1px solid #393939; border-radius: 10px; background: #191919; }
.asset-tile .hero-sprite { width: 45px; height: 58px; }
.asset-tile span { color: #737b87; font: 8px ui-monospace, SFMono-Regular, Menlo, monospace; text-transform: uppercase; }
.asset-meta { display: flex; gap: 8px; margin-top: 9px; }
.asset-meta span { flex: 1; padding: 6px 7px; border: 1px solid #343434; border-radius: 7px; color: #6b7280; background: #181818; font: 8px ui-monospace, SFMono-Regular, Menlo, monospace; text-align: center; }

.flow-progress { position: absolute; z-index: 12; right: 22px; bottom: 18px; left: 22px; display: grid; grid-template-columns: repeat(5, 1fr); gap: 7px; }
.flow-step { position: relative; padding-top: 11px; color: #555d69; font: 8px ui-monospace, SFMono-Regular, Menlo, monospace; letter-spacing: 0.04em; text-align: center; text-transform: uppercase; transition: color 0.35s ease; }
.flow-step::before { position: absolute; top: 0; right: 0; left: 0; height: 2px; border-radius: 2px; background: #343434; transition: background 0.35s ease, box-shadow 0.35s ease; content: ''; }
.flow-step.active { color: #9fc9e9; }
.flow-step.active::before { background: #ffbd5c; box-shadow: 0 0 12px rgb(255 189 92 / 75%); }

@media (max-width: 520px) {
  .creation-flow { min-height: 350px; }
  .flow-stage { right: 15px; left: 15px; }
  .combo-card { grid-template-columns: 112px 1fr; }
  .asset-grid { gap: 5px; }
  .flow-step { font-size: 7px; }
}

@media (prefers-reduced-motion: reduce) {
  .flow-stage-enter-active,
  .flow-stage-leave-active,
  .prompt-caret,
  .art-board::after,
  .combo-wave i,
  .animation-main .hero-sprite {
    animation: none;
  }
}
</style>
