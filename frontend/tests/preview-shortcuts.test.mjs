import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { closeSfcRenderer, renderSfc } from './vue-render-helper.mjs';

after(closeSfcRenderer);

const copy = {
  'zh-CN': {
    preview: ['移动画布 (V)', '放大 (↑)', '缩小 (↓)', '居中 (R)'],
    previous: '上一帧 (←)',
    next: '下一帧 (→)',
    play: '播放 (Space)',
    pause: '暂停 (Space)',
  },
  en: {
    preview: ['Pan canvas (V)', 'Zoom in (↑)', 'Zoom out (↓)', 'Center (R)'],
    previous: 'Previous frame (←)',
    next: 'Next frame (→)',
    play: 'Play (Space)',
    pause: 'Pause (Space)',
  },
};

function tooltipLabels(html) {
  return Array.from(html.matchAll(/<button\b[^>]*>/g), ([button]) => {
    if (!button.includes('control-tooltip')) return null;
    return button.match(/\sdata-tooltip="([^"]*)"/)?.[1]
      ?? button.match(/\saria-label="([^"]*)"/)?.[1]
      ?? null;
  }).filter(Boolean);
}

test('preview controls expose localized shortcut hints and dynamic playback wording', async () => {
  for (const [locale, expected] of Object.entries(copy)) {
    for (const retouchEnabled of [false, true]) {
      const html = await renderSfc('components/player/FramePlayer.vue', {
        locale,
        props: { retouchEnabled },
      });
      const labels = tooltipLabels(html);
      for (const hint of expected.preview) {
        assert.ok(labels.includes(hint), `${locale} must show ${hint}; received ${labels.join(', ')}`);
      }
    }

    for (const isPlaying of [false, true]) {
      const html = await renderSfc('components/player/PlayerControls.vue', {
        locale,
        piniaState: { player: { frames: [], isPlaying, startFrame: 0, endFrame: 0, currentIndex: 0 } },
      });
      const labels = tooltipLabels(html);
      for (const hint of [expected.previous, expected.next, isPlaying ? expected.pause : expected.play]) {
        assert.ok(labels.includes(hint), `${locale} must show ${hint}; received ${labels.join(', ')}`);
      }
      assert.ok(!labels.includes(isPlaying ? expected.play : expected.pause));
    }
  }
});
