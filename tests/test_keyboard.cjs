// Run with node --test tests/test_keyboard.cjs (no browser dependencies).
const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const source = fs.readFileSync('studio/static/studio.js', 'utf8').split('// Keyboard edits share')[1];
function setup() {
  const elements = new Map();
  const calls = [];
  const el = id => {
    if (!elements.has(id)) elements.set(id, {checked:false, hidden:false, children:[], click(){calls.push(id);}, replaceChildren(){this.children=[];}, append(b){this.children.push(b);}, showModal(){this.open=true;}, close(){this.open=false;}});
    return elements.get(id);
  };
  class Element { closest(){return this.typing;} }
  const context = {Element, $, graph:{pipes:[{u:[0,0,0],v:[0,0,1]}]}, selectedPipe:'0,0,0|0,0,1', selected:null, generation:0, busy:false, drag:null,
    clone:structuredClone, pipeKey:p=>[p.u.join(','),p.v.join(',')].sort().join('|'),
    message:t=>calls.push(t), render(){}, deletePipe:p=>calls.push(['delete',p]),
    placePipe:async (p,k)=>calls.push(['place',p,k]),
    api:async()=>({placements:[]}),
    document:{querySelector:()=>false, createElement:()=>({}), addEventListener:(_,fn)=>context.handle=fn}};
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
  const s=setup(); s.press('Delete'); s.press('f');
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
test('multiple valid choices require selection; stale requests do not edit',async()=>{
  const s=setup(); const option={u:[0,0,1],v:[1,0,1]};
  s.context.api=async()=>({placements:[option]});
  await s.context.extendByKeyboard(0,1);
  assert.equal(s.el('direction-options').children.length,2);
  assert.equal(s.el('direction-dialog').open,true);
  assert.ok(!s.calls.some(x=>Array.isArray(x)&&x[0]==='place'));
  s.context.generation++;
  await s.el('direction-options').children[0].onclick();
  assert.ok(!s.calls.some(x=>Array.isArray(x)&&x[0]==='place'));
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
