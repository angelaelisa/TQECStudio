const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
function viewer() {
  const items = new Map();
  function element(id) {
    if (!items.has(id)) items.set(id, {style:{}, value:0, listeners:{}, naturalWidth:1000, naturalHeight:800, clientWidth:600, clientHeight:400, scrollTop:0, scrollLeft:0, addEventListener(name, callback){this.listeners[name]=callback;}});
    return items.get(id);
  }
  const context = {document:{body:{dataset:{ticks:'10',job:'abc'}}, getElementById:element}, ResizeObserver:class {observe(){}}};
  vm.createContext(context);
  vm.runInContext(fs.readFileSync('studio/static/physical_layers.js','utf8'), context);
  return {element, context};
}
test('fit keeps the full diagram in view and manual zoom carries across slices',()=>{
  const {element}=viewer();
  const image=element('physical-image'); image.listeners.load();
  assert.equal(image.style.width,'460px');
  assert.equal(image.style.height,'368px');
  element('physical-zoom-in').onclick();
  const width=image.style.width;
  element('next-slice').onclick(); image.listeners.load();
  assert.equal(image.style.width,width);
  element('physical-actual-size').onclick();
  assert.equal(image.style.width,'1000px');
  element('physical-fit').onclick();
  assert.equal(image.style.width,'460px');
});
test('zoom limits and wheel scrolling protect ordinary page navigation',()=>{
  const {element}=viewer();
  element('physical-image').listeners.load();
  let prevented=false;
  const viewport=element('physical-viewport');
  viewport.listeners.wheel({ctrlKey:false,metaKey:false,preventDefault(){prevented=true;}});
  assert.equal(prevented,false);
  viewport.listeners.wheel({ctrlKey:true,deltaY:100,deltaMode:0,preventDefault(){prevented=true;}});
  assert.equal(prevented,true);
  const slider=element('physical-zoom'); slider.value=10000; slider.oninput();
  assert.equal(element('physical-image').style.width,'4000px');
  assert.equal(element('physical-zoom-in').disabled,true);
  slider.value=0; slider.oninput();
  assert.equal(element('physical-image').style.width,'50px');
  assert.equal(element('physical-zoom-out').disabled,true);
});
