// Run with node --test tests/test_keyboard.cjs (no browser dependencies).
const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const fullSource = fs.readFileSync('studio/static/studio.js', 'utf8');
const source = fullSource.split('// Keyboard edits share')[1];
function setup() {
  const elements = new Map();
  const calls = [];
  const el = id => {
    if (!elements.has(id)) elements.set(id, {checked:false, hidden:false, children:[], click(){calls.push(id);}, replaceChildren(){this.children=[];}, append(b){this.children.push(b);}, showModal(){this.open=true;}, close(){this.open=false;}});
    return elements.get(id);
  };
  class Element { closest(){return this.typing;} }
  const context = {Element, $, graph:{cubes:[{position:[0,0,0]},{position:[0,0,1]}],pipes:[{u:[0,0,0],v:[0,0,1]}]}, selectedPipe:null, selected:'0,0,1', kind:'ZXO', generation:0, busy:false, drag:null,
    clone:structuredClone, key:p=>p.join(','), pipeKey:p=>[p.u.join(','),p.v.join(',')].sort().join('|'),
    message:t=>calls.push(t), render(){}, deletePipe:p=>calls.push(['delete',p]),
    placePipe:async (p,k,choices,focus)=>calls.push(['place',p,k,focus]),
    api:async()=>({placements:[]}),
    document:{querySelector:()=>false, querySelectorAll:()=>[], createElement:()=>({}), addEventListener:(_,fn)=>context.handle=fn}};
  function $(id){return el(id);}
  vm.createContext(context);
  vm.runInContext('// Keyboard edits share'+source, context);
  const press = (key, extras={}) => context.handle({key,target:new Element(),preventDefault(){calls.push('prevented');},...extras});
  return {context,calls,el,press,Element};
}
test('undo, both redo bindings, and typing guards',()=>{
  const s=setup();
  s.press('z',{metaKey:true}); s.press('y',{ctrlKey:true}); s.press('Z',{metaKey:true,shiftKey:true});
  assert.deepEqual(s.calls.filter(x=>x==='undo'||x==='redo'),['undo','redo','redo']);
  s.calls.length=0;
  const target=new s.Element(); target.typing=true;
  s.press('z',{ctrlKey:true,target}); s.press('x',{repeat:true}); s.press('y',{isComposing:true});
  assert.equal(s.calls.length,0);
});
test('selected pipe deletion, fit and modal guards',()=>{
  const s=setup(); s.context.selectedPipe='0,0,0|0,0,1'; s.context.selected=null; s.press('Delete'); s.press('f');
  assert.equal(s.calls[1][0],'delete'); assert.ok(s.calls.includes('fit'));
  s.context.document.querySelector=()=>true; s.calls.length=0; s.press('Delete');
  assert.equal(s.calls.length,0);
});
test('six directions match validated edges and preserve Hadamard choice',async()=>{
  for(let axis=0;axis<3;axis++) for(const sign of [-1,1]) {
    const s=setup(); const u=[0,0,1], v=[...u]; v[axis]+=sign;
    const option={u,v}; s.el('hadamard').checked=true;
    let count=0;
    s.context.api=async(_,data)=>({placements:count++===0?[option]:[]});
    await s.context.extendByKeyboard(axis,sign);
    const placement=s.calls.find(x=>Array.isArray(x)&&x[0]==='place');
    assert.ok(placement); assert.ok(placement[2].endsWith('H')); assert.equal(placement[2][axis],'O');
  }
});
test('two compatible colours use the palette without an endpoint dialog',async()=>{
  const s=setup(); const option={u:[0,0,1],v:[1,0,1]};
  s.context.kind='OZX';
  s.context.api=async()=>({placements:[option,{u:[0,0,0],v:[1,0,0]}]});
  await s.context.extendByKeyboard(0,1);
  const placement=s.calls.find(x=>Array.isArray(x)&&x[0]==='place');
  assert.equal(placement[2],'OZX');
  assert.deepEqual(Array.from(placement[3]),[1,0,1]);
  assert.equal(s.el('direction-dialog').open,undefined);
});
test('stale selection or graph responses do not place a pipe',async()=>{
  for (const update of [c=>c.generation++,c=>c.selected='0,0,0',c=>c.selectedPipe='0,0,0|0,0,1']) {
    const s=setup();
    s.context.api=async()=>{update(s.context);return {placements:[{u:[0,0,1],v:[1,0,1]}]};};
    await s.context.extendByKeyboard(0,1);
    assert.ok(!s.calls.some(x=>Array.isArray(x)&&x[0]==='place'));
  }
});
test('a valid edge from another cube never extends the selected cube',async()=>{
  const s=setup();
  s.context.api=async()=>({placements:[{u:[0,0,0],v:[1,0,0]}]});
  await s.context.extendByKeyboard(0,1);
  assert.ok(!s.calls.some(x=>Array.isArray(x)&&x[0]==='place'));
  assert.match(s.calls.at(-1),/selected cube/);
  s.context.selected=null;
  await s.context.extendByKeyboard(0,1);
  assert.match(s.calls.at(-1),/Select a cube, open port or pipe/);
});
test('placement focuses the destination for positive, negative and joined edges',async()=>{
  for (const destination of [[1,0,1],[-1,0,1],[0,0,0]]) {
    const s=setup();
    vm.runInContext(fullSource.slice(fullSource.indexOf('async function placePipe('),fullSource.indexOf("$('build-mode').querySelector")),s.context);
    s.context.commit=next=>{s.context.graph=next;};
    s.context.scrollToSelectedPipe=()=>{};
    s.context.api=async()=>({graph:{cubes:[...s.context.graph.cubes,{position:destination}],pipes:[]},inferred:[]});
    await s.context.placePipe({u:[0,0,1],v:destination},'OXZ',{},destination);
    assert.equal(s.context.selected,destination.join(','));
    assert.equal(s.context.selectedPipe,null);
  }
});

test('cube deletion uses the existing delete action for both keys and respects typing',()=>{
  for (const key of ['Delete', 'Backspace']) {
    const s=setup(); s.context.selectedPipe=null; s.context.selected='0,0,0';
    s.press(key);
    assert.deepEqual(s.calls,['prevented','delete']);
    s.calls.length=0;
    const target=new s.Element(); target.typing=true;
    s.press(key,{target});
    assert.equal(s.calls.length,0);
    s.context.selected=null; s.press(key);
    assert.equal(s.calls.length,0);
  }
});

test('active pipes extend from the farther end on positive and negative axes, including turns',async()=>{
  for (const [u,v,axis,sign,expected] of [
    [[0,0,0],[0,0,1],2,1,[0,0,1]],
    [[-4,0,0],[-3,0,0],0,-1,[-4,0,0]],
    [[0,0,0],[0,0,1],0,1,[0,0,1]],
    [[0,0,1],[0,0,0],0,-1,[0,0,1]],
    [[-1,0,0],[1,0,0],0,-1,[-1,0,0]],
    [[-1,0,0],[1,0,0],0,1,[1,0,0]],
  ]) {
    const s=setup();
    s.context.selected=null;
    s.context.graph.pipes=[{u,v}];
    s.context.selectedPipe=s.context.pipeKey({u,v});
    const destination=[...expected]; destination[axis]+=sign;
    const option={u:expected,v:destination};
    s.context.api=async()=>({placements:[option]});
    await s.context.extendByKeyboard(axis,sign);
    const placement=s.calls.find(x=>Array.isArray(x)&&x[0]==='place');
    assert.ok(placement);
    assert.equal(placement[3],null,'pipe selection continues as a pipe, not an automatic cube click');
  }
});
test('blocked farther endpoint does not silently switch to the other pipe end',async()=>{
  const s=setup(); s.context.selected=null; s.context.selectedPipe='0,0,0|0,0,1';
  s.context.api=async()=>({placements:[{u:[0,0,0],v:[1,0,0]}]});
  await s.context.extendByKeyboard(0,1);
  assert.ok(!s.calls.some(x=>Array.isArray(x)&&x[0]==='place'));
  assert.match(s.calls.at(-1),/chosen endpoint \(0, 0, 1\)/);
});
test('normal placement keeps the new pipe active for building through open ports',async()=>{
  const s=setup();
  vm.runInContext(fullSource.slice(fullSource.indexOf('async function placePipe('),fullSource.indexOf("$('build-mode').querySelector")),s.context);
  s.context.commit=next=>{s.context.graph=next;};
  s.context.scrollToSelectedPipe=()=>{};
  s.context.api=async()=>({graph:{cubes:s.context.graph.cubes,pipes:[{u:[0,0,1],v:[1,0,1]}]},inferred:[]});
  await s.context.placePipe({u:[0,0,1],v:[1,0,1]},'OXZ');
  assert.equal(s.context.selected,null);
  assert.equal(s.context.selectedPipe,'0,0,1|1,0,1');
});
