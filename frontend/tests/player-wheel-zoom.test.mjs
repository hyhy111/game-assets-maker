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

async function player(editing, step = editing ? 3 : 1) {
  createScriptedPyWebViewBridge({});
  const {usePlayerStore} = await loadFrontendModule('/src/stores/player.ts');
  const {useProcessStore} = await loadFrontendModule('/src/stores/process.ts');
  setActivePinia(createPinia());
  const store = usePlayerStore();
  const process = useProcessStore();
  process.currentStep = step;
  const props = {editing};
  const setup = new Function('ref','computed','watch','onMounted','onUnmounted','storeToRefs','usePlayerStore',
    'useI18n','defineProps','withDefaults','defineEmits','ZoomIn','ZoomOut','Scan',
    `${javascript}\nreturn {containerRef, canvasRef, handleWheel, handleKeydown, handleKeyup, handleMouseDown, handleMouseMove, handleMouseUp, zoomControls};`);
  const bindings = setup(ref,computed,()=>{},()=>{},()=>{},storeToRefs,()=>store,()=>({t:k=>k}),
    ()=>props, p=>p,()=>()=>{},null,null,null);
  bindings.containerRef.value = {getBoundingClientRect:()=>({left:100,top:50,width:800,height:600})};
  const wheel = (deltaY, clientX=700, clientY=200) => bindings.handleWheel({deltaY,clientX,clientY,preventDefault(){}});
  return {store,props,wheel,...bindings};
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

for (const step of [1, 2, 3]) {
  test(`R centers and fits in step ${step}, while Cmd/Ctrl+0 and guarded R events do nothing`, async () => {
    const state = await player(step === 3, step);
    const {store,props,containerRef,canvasRef,zoomControls,handleKeydown} = state;
    canvasRef.value = {width:1920,height:1080};
    const canvas = canvasRef.value;
    containerRef.value = {getBoundingClientRect:()=>({width:800,height:420})};
    const reset = zoomControls.find(control=>control.action==='reset').handler;
    store.setZoom(2); store.setPan(250,-160);
    reset();
    assert.ok(canvas.height * store.zoom <= 420, 'reset must fit below the retouch toolbar');
    assert.ok(canvas.width * store.zoom <= 800);
    assert.equal(store.panX,0); assert.equal(store.panY,0);
    const buttonZoom = store.zoom;

    const previousElement = globalThis.Element;
    globalThis.Element = class {
      constructor(editable = false) { this.editable = editable; }
      closest() { return this.editable; }
    };
    const press = (key, options = {}) => {
      const event = {key,target:null,preventDefault(){ this.defaultPrevented = true; },...options};
      handleKeydown(event);
      return event;
    };
    const assertUnchanged = (event, alreadyPrevented = false) => {
      assert.equal(store.zoom,2);
      assert.equal(store.panX,42); assert.equal(store.panY,-37);
      assert.equal(event.defaultPrevented,alreadyPrevented ? true : undefined);
    };
    try {
      store.setZoom(2); store.setPan(42,-37);
      assert.equal(press('r').defaultPrevented,true);
      assert.equal(store.zoom,buttonZoom, 'keyboard reset uses the same viewport fit');
      assert.equal(store.panX,0); assert.equal(store.panY,0);

      for (const modifier of ['ctrlKey','metaKey']) {
        store.setZoom(2); store.setPan(42,-37);
        assertUnchanged(press('0',{[modifier]:true}));
      }
      for (const options of [
        {ctrlKey:true}, {metaKey:true}, {altKey:true}, {shiftKey:true}, {repeat:true},
        {isComposing:true}, {defaultPrevented:true}, {target:new globalThis.Element(true)},
      ]) {
        store.setZoom(2); store.setPan(42,-37);
        assertUnchanged(press('r',options), options.defaultPrevented);
      }
      for (const guard of ['keyboardDisabled','toolsDisabled']) {
        props[guard] = true;
        store.setZoom(2); store.setPan(42,-37);
        assertUnchanged(press('r'));
        props[guard] = false;
      }
    } finally {
      if (previousElement === undefined) delete globalThis.Element;
      else globalThis.Element = previousElement;
    }
    containerRef.value = {getBoundingClientRect:()=>({width:800,height:300})};
    reset();
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

for (const editing of [false, true]) {
  test(`middle-drag panning remains available in ${editing ? 'retouch' : 'browse'} mode`, async () => {
    const {store,handleMouseDown,handleMouseMove,handleMouseUp} = await player(editing);
    store.setPan(10,-5);
    const down = {button:1,clientX:100,clientY:80,preventDefault(){ this.defaultPrevented = true; }};
    handleMouseDown(down);
    assert.equal(down.defaultPrevented,true);
    assert.equal(store.isDragging,true);
    handleMouseMove({clientX:145,clientY:60});
    assert.equal(store.panX,55); assert.equal(store.panY,-25);
    handleMouseUp();
    assert.equal(store.isDragging,false);
    handleMouseMove({clientX:200,clientY:200});
    assert.equal(store.panX,55); assert.equal(store.panY,-25);
  });

  test(`Space, frame arrows and zoom arrows retain their ${editing ? 'retouch' : 'browse'} behavior`, async () => {
    const {store,handleKeydown,handleKeyup} = await player(editing);
    store.frames = [0,1,2].map(index => ({filename:`${index}.png`,path:`${index}.png`,url:`data:${index}`}));
    store.startFrame = 0; store.endFrame = 2; store.currentIndex = 1; store.frameInterval = 1;
    const previousElement = globalThis.Element;
    globalThis.Element = class {};
    try {
      let playToggles = 0;
      store.togglePlay = () => { playToggles += 1; };
      const press = (key, options = {}) => {
        const event = {key,target:null,preventDefault(){ this.defaultPrevented = true; },...options};
        handleKeydown(event);
        return event;
      };
      assert.equal(press(' ').defaultPrevented,true);
      assert.equal(playToggles,1);
      assert.equal(press(' ',{repeat:true}).defaultPrevented,true);
      assert.equal(playToggles,1);
      const zoom = store.zoom;
      press('ArrowUp'); assert.equal(store.zoom,zoom * 1.2);
      press('ArrowDown'); assert.equal(store.zoom,zoom);
      press('ArrowRight'); assert.equal(store.currentIndex,2);
      handleKeyup({key:'ArrowRight'});
      press('ArrowLeft'); assert.equal(store.currentIndex,1);
      handleKeyup({key:'ArrowLeft'});
    } finally {
      if (previousElement === undefined) delete globalThis.Element;
      else globalThis.Element = previousElement;
    }
  });
}

for (const editing of [false, true]) {
  test(`Space toggles playback after a button receives focus in ${editing ? 'retouch' : 'browse'} mode`, async () => {
    const {store,props,handleKeydown} = await player(editing);
    const previousElement = globalThis.Element;
    globalThis.Element = class {
      constructor(tagName, parent = null) { this.tagName = tagName; this.parent = parent; }
      closest(selector) {
        return selector.split(',').map(s => s.trim()).includes(this.tagName)
          ? this : this.parent?.closest(selector) ?? null;
      }
    };
    try {
      let playToggles = 0;
      store.togglePlay = () => { playToggles += 1; };
      const press = (target, options = {}) => {
        const event = {key:' ',target,preventDefault(){ this.defaultPrevented = true; },...options};
        handleKeydown(event);
        return event;
      };
      const button = new Element('button');
      for (const target of [button, new Element('svg', button)]) {
        const before = playToggles;
        assert.equal(press(target).defaultPrevented,true, 'Space must suppress native button activation');
        assert.equal(playToggles,before + 1);
        assert.equal(press(target,{repeat:true}).defaultPrevented,true);
        assert.equal(playToggles,before + 1, 'holding Space must not toggle again');
      }
      const before = playToggles;
      for (const tag of ['input','textarea','select','[contenteditable="true"]']) {
        assert.equal(press(new Element(tag)).defaultPrevented,undefined);
      }
      press(button,{defaultPrevented:true});
      props.keyboardDisabled = true;
      assert.equal(press(button).defaultPrevented,undefined);
      assert.equal(playToggles,before);
    } finally {
      if (previousElement === undefined) delete globalThis.Element;
      else globalThis.Element = previousElement;
    }
  });
}
