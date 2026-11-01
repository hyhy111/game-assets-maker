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
    `${javascript}\nreturn {containerRef, canvasRef, handleWheel, handleKeydown, zoomControls};`);
  const bindings = setup(ref,computed,()=>{},()=>{},()=>{},storeToRefs,()=>store,()=>({t:k=>k}),
    ()=>({editing}), p=>p,()=>()=>{},null,null,null);
  bindings.containerRef.value = {getBoundingClientRect:()=>({left:100,top:50,width:800,height:600})};
  const wheel = (deltaY, clientX=700, clientY=200) => bindings.handleWheel({deltaY,clientX,clientY,preventDefault(){}});
  return {store,wheel,...bindings};
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

for (const editing of [false, true]) {
  test(`reset fits the actual shortened viewport and centers the whole frame in ${editing ? 'retouch' : 'browse'} mode`, async () => {
    const state = await player(editing);
    const {store,containerRef,canvasRef,zoomControls,handleKeydown} = state;
    canvasRef.value = {width:1920,height:1080};
    const canvas = canvasRef.value;
    containerRef.value = {getBoundingClientRect:()=>({width:800,height:420})};
    store.setZoom(2); store.setPan(250,-160);
    zoomControls.find(control=>control.action==='reset').handler();
    assert.ok(canvas.height * store.zoom <= 420, 'reset must fit below the retouch toolbar');
    assert.ok(canvas.width * store.zoom <= 800);
    assert.equal(store.panX,0); assert.equal(store.panY,0);
    const buttonZoom = store.zoom;
    store.setZoom(2); store.setPan(42,-37);
    const previousElement = globalThis.Element;
    globalThis.Element = class {};
    try {
      handleKeydown({key:'0',ctrlKey:true,target:null,preventDefault(){}});
      assert.equal(store.zoom,buttonZoom, 'keyboard reset uses the same viewport fit');
    } finally {
      if (previousElement === undefined) delete globalThis.Element;
      else globalThis.Element = previousElement;
    }
    containerRef.value = {getBoundingClientRect:()=>({width:800,height:300})};
    zoomControls.find(control=>control.action==='reset').handler();
    assert.ok(store.zoom<buttonZoom, 'reset recalculates after the available height shrinks');
    assert.ok(canvas.height * store.zoom<=300);
    assert.deepEqual({width:canvas.width,height:canvas.height},{width:1920,height:1080});
  });
}

test('reset fits wide frames, keeps small frames at native size and tolerates an unloaded canvas', async () => {
  const {store,canvasRef,containerRef,zoomControls} = await player(false);
  const reset = zoomControls.find(control=>control.action==='reset').handler;
  containerRef.value = {getBoundingClientRect:()=>({width:600,height:400})};
  canvasRef.value = {width:3200,height:500};
  reset();
  assert.ok(3200 * store.zoom<=600);
  assert.ok(500 * store.zoom<=400);
  canvasRef.value = {width:64,height:64};
  reset();
  assert.equal(store.zoom,1);
  canvasRef.value = undefined;
  store.setPan(20,30); reset();
  assert.equal(store.zoom,1); assert.equal(store.panX,0); assert.equal(store.panY,0);
});
