import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { after, test } from 'node:test';
import ts from 'typescript';
import { computed, ref } from 'vue';
import { createPinia, setActivePinia, storeToRefs } from 'pinia';
import { closeFrontendHarness, createScriptedPyWebViewBridge, loadFrontendModule } from './scripted-pywebview-bridge.mjs';

after(closeFrontendHarness);
const source = await readFile(new URL('../src/components/player/FramePlayer.vue', import.meta.url), 'utf8');
const script = source.match(/<script setup lang="ts">([\s\S]*?)<\/script>/)[1].replace(/^import .*;$/gm, '');
const javascript = ts.transpileModule(script, {compilerOptions:{target:ts.ScriptTarget.ES2022}}).outputText;

async function player(editing) {
  createScriptedPyWebViewBridge({});
  const {usePlayerStore} = await loadFrontendModule('/src/stores/player.ts');
  setActivePinia(createPinia());
  const store = usePlayerStore();
  const setup = new Function('ref','computed','watch','onMounted','onUnmounted','storeToRefs','usePlayerStore',
    'useI18n','defineProps','withDefaults','defineEmits','ZoomIn','ZoomOut','Maximize',
    `${javascript}\nreturn {containerRef, handleWheel};`);
  const bindings = setup(ref,computed,()=>{},()=>{},()=>{},storeToRefs,()=>store,()=>({t:k=>k}),
    ()=>({editing}), p=>p,()=>()=>{},null,null,null);
  bindings.containerRef.value = {getBoundingClientRect:()=>({left:100,top:50,width:800,height:600})};
  const wheel = (deltaY, clientX=700, clientY=200) => bindings.handleWheel({deltaY,clientX,clientY,preventDefault(){}});
  return {store,wheel};
}

for (const editing of [false,true]) {
  test(`wheel zoom keeps the image coordinate under the pointer in ${editing ? 'retouch' : 'browse'} mode`, async () => {
    const {store,wheel} = await player(editing);
    store.setZoom(0.8); store.setPan(40,-35);
    const point = () => [(700-100-400-store.panX)/store.zoom, (200-50-300-store.panY)/store.zoom];
    const before = point();
    for (const delta of [-1,-1,1,1]) {
      wheel(delta);
      point().forEach((v,i)=>assert.ok(Math.abs(v-before[i])<1e-9));
    }
  });
}

test('zoom clamps to actual store limits without anchor drift or zero-wheel motion', async () => {
  const {store,wheel} = await player(true);
  for (const [zoom,delta] of [[5,-1],[0.1,1]]) {
    store.setZoom(zoom); store.setPan(23,-47);
    wheel(delta);
    assert.equal(store.zoom, zoom);
    assert.equal(store.panX,23); assert.equal(store.panY,-47);
  }
  store.setZoom(4.9); store.setPan(23,-47);
  const before=(200-store.panX)/store.zoom;
  wheel(-1);
  assert.equal(store.zoom,5);
  assert.ok(Math.abs((200-store.panX)/store.zoom-before)<1e-9);
  const state=[store.zoom,store.panX,store.panY];
  wheel(0);
  assert.deepEqual([store.zoom,store.panX,store.panY],state);
});
