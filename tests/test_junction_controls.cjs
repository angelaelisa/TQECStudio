const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const source = fs.readFileSync('studio/static/studio.js', 'utf8');
function setup() {
  const elements = new Map();
  const calls = [];
  const el = id => {
    if (!elements.has(id)) elements.set(id, {
      children: [], open: false, handlers: {},
      replaceChildren() {this.children = [];}, append(row) {this.children.push(row);},
      showModal() {this.open = true;}, close() {this.open = false;},
      addEventListener(name, fn) {this.handlers[name] = fn;}
    });
    return elements.get(id);
  };
  const initial = {cubes:[{position:[0,0,0],kind:'ZXZ'}],pipes:[{u:[0,0,0],v:[0,1,0],kind:'ZOX'}]};
  const context = {graph: structuredClone(initial), history: [], future: [], generation: 0,
    busy: false, pendingCubeRepair: null, pendingPipe: null, selected:null, selectedPipe:null,
    $:el, clone:structuredClone, pipeKey:p=>[p.u.join(','),p.v.join(',')].sort().join('|'),
    key:p=>p.join(','), saveDraft(){}, render(){},
    invalidate(){context.generation++;context.pendingCubeRepair=null;},
    message:(...args)=>calls.push(args),
    api:async(path)=>path==='/api/graph'?{revision:'revision'}:{
      graph:{...structuredClone(initial),cubes:[{position:[0,0,0],kind:'ZXX'}]},
      changes:[{position:[0,0,0],before:'ZXZ',after:'ZXX'}]},
    showJunctionChoices:(ambiguities,pending)=>{context.pendingPipe=pending;},
    document:{createElement:()=>({})}};
  vm.createContext(context);
  vm.runInContext(source.slice(source.indexOf('function commit('),source.indexOf('async function change(')),context);
  vm.runInContext(source.split('// Cube repair controls:')[1].split('// End cube repair controls.')[0].replace(/^.*\n/,''),context);
  vm.runInContext(source.slice(source.indexOf('async function deletePipe('),source.indexOf('function setupPipeSelection(')),context);
  vm.runInContext(source.slice(source.indexOf("$('undo').onclick"),source.indexOf("$('name').onchange")),context);
  return {context,el,calls,initial};
}
test('repair is previewed, cancel preserves graph, apply supports undo and redo',async()=>{
  const s=setup();
  await s.context.reviewCubeRepairs();
  assert.equal(s.el('cube-repair-dialog').open,true);
  assert.match(s.el('cube-repair-changes').children[0].textContent,/ZXZ → ZXX/);
  assert.deepEqual(s.context.graph,s.initial);
  s.el('cancel-cube-repair').onclick();
  assert.deepEqual(s.context.graph,s.initial);
  await s.context.reviewCubeRepairs();
  s.el('apply-cube-repair').onclick();
  assert.equal(s.context.graph.cubes[0].kind,'ZXX');
  assert.equal(s.context.history.length,1);
  s.el('undo').onclick(); assert.deepEqual(s.context.graph,s.initial);
  s.el('redo').onclick(); assert.equal(s.context.graph.cubes[0].kind,'ZXX');
});
test('stale repair responses and stale previews cannot overwrite newer graph edits',async()=>{
  const s=setup();
  await s.context.reviewCubeRepairs(); s.context.generation++;
  s.el('apply-cube-repair').onclick(); assert.equal(s.context.history.length,0);
  s.context.api=async(path)=>{s.context.generation++;return {revision:'new',changes:[],graph:{}};};
  await s.context.reviewCubeRepairs(); assert.equal(s.context.pendingCubeRepair,null);
});
test('pipe deletion applies validated cube changes in one undoable edit',async()=>{
  const s=setup();
  s.context.api=async(path)=>{
    assert.equal(path,'/api/delete-pipe');
    return {graph:{cubes:[{position:[0,0,0],kind:'ZXX'}],pipes:[]},inferred:[{position:[0,0,0],previous:'ZXZ',kind:'ZXX'}]};
  };
  await s.context.deletePipe('0,0,0|0,1,0');
  assert.equal(s.context.graph.pipes.length,0);
  assert.equal(s.context.graph.cubes[0].kind,'ZXX');
  assert.equal(s.context.history.length,1);
  s.el('undo').onclick(); assert.deepEqual(s.context.graph,s.initial);
});
test('failed or ambiguous deletion leaves graph untouched',async()=>{
  const s=setup();
  s.context.api=async()=>{throw Error('Invalid junction');};
  await s.context.deletePipe('0,0,0|0,1,0'); assert.deepEqual(s.context.graph,s.initial);
  s.context.api=async()=>({ambiguities:[{position:[0,0,0],kinds:['ZXZ','ZXX']}]});
  await s.context.deletePipe('0,0,0|0,1,0');
  assert.equal(s.context.pendingPipe.action,'delete');
  assert.deepEqual(s.context.graph,s.initial);
  assert.equal(s.context.history.length,0);
});
