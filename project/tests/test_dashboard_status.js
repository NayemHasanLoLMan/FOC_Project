// Run with Node; uses only its standard library and a small DOM stand-in.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const nodes = new Map();
for (const selector of ['#web-status','#queue-state','#activity-title','#refreshed',
  '[data-health="scanner"]','[data-health="worker"]','[data-health="ollama"]']) {
  nodes.set(selector,{textContent:'',dataset:{}});
}
const status = {queue:{paused:false},counts:{},intake_counts:{},today:{},
  scanner:{state:'running'},worker:{state:'running'},active:{job_id:2}};
let failed = false;
let modelState = 'available';
const context = vm.createContext({AbortSignal,setInterval:()=>{},
  document:{hidden:true,addEventListener:()=>{},querySelector:()=>null,
    querySelectorAll:selector=>selector==='[data-health]'
      ? [...nodes].filter(([key])=>key.startsWith('[data-health=')).map(([,node])=>node)
      : nodes.has(selector) ? [nodes.get(selector)] : []},
  fetch:async url=>{
    if (failed) throw new Error('Connection failed');
    return {ok:true,json:async()=>url==='/api/ollama' ? {state:modelState} : status};
  }});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../frontend/static/dashboard.js'),'utf8'),context);
async function check() {
  vm.runInContext('document.hidden=false',context);
  await vm.runInContext('refresh()',context);
  assert.equal(nodes.get('[data-health="worker"]').dataset.state,'running');
  assert.equal(nodes.get('#activity-title').dataset.state,'running');
  assert.equal(nodes.get('#queue-state').dataset.state,'ready');
  status.queue.paused=true;status.scanner.state='degraded';status.worker.state='failed';
  await vm.runInContext('refresh()',context);
  assert.equal(nodes.get('#queue-state').dataset.state,'paused');
  assert.equal(nodes.get('[data-health="scanner"]').dataset.state,'degraded');
  assert.equal(nodes.get('[data-health="worker"]').dataset.state,'failed');
  assert.equal(nodes.get('#activity-title').dataset.state,'unknown');
  for (const value of ['available','model_missing','unavailable','disabled']) {
    modelState=value;await vm.runInContext('refreshModel()',context);
    assert.equal(nodes.get('[data-health="ollama"]').dataset.state,value);
  }
  failed=true;await vm.runInContext('refresh()',context);
  assert.equal(nodes.get('#web-status').dataset.state,'error');
  assert.equal(nodes.get('#queue-state').dataset.state,'unknown');
  for(const component of ['scanner','worker','ollama']) {
    assert.equal(nodes.get('[data-health="'+component+'"]').dataset.state,'unknown');
  }
  failed=false;status.worker.state='running';status.queue.paused=false;
  await vm.runInContext('refresh()',context);
  assert.equal(nodes.get('#web-status').dataset.state,'available');
  assert.equal(nodes.get('[data-health="worker"]').dataset.state,'running');
  const select = {value:'qwen3-vl:latest',dataset:{},options:[],replaceChildren(...options){this.options=options;}};
  const hint = {textContent:''};
  context.Option = function(text,value){this.text=text;this.value=value;};
  context.document.querySelector = selector => selector==='#vision-model' ? select : null;
  const previousAll = context.document.querySelectorAll;
  context.document.querySelectorAll = selector => selector==='#model-list-status' ? [hint] : previousAll(selector);
  vm.runInContext('updateModelOptions({model_list_available:true,models:["qwen3:latest","qwen3-vl:latest"]})',context);
  assert.equal(select.value,'qwen3-vl:latest');
  assert.deepEqual(select.options.map(option=>option.value),['','qwen3-vl:latest','qwen3:latest']);
  select.value='qwen3:latest';
  vm.runInContext('updateModelOptions({model_list_available:true,models:["qwen3:latest","qwen3-vl:latest"]})',context);
  assert.equal(select.value,'qwen3:latest');
  vm.runInContext('updateModelOptions({model_list_available:false})',context);
  assert.equal(select.value,'qwen3:latest');
  assert.match(hint.textContent,/unavailable/);
  vm.runInContext('updateModelOptions({model_list_available:true,models:[]})',context);
  assert.equal(select.value,'qwen3:latest');
  assert.match(select.options[1].text,/unavailable/);
  select.value='';
  vm.runInContext('updateModelOptions({model_list_available:true,models:["new-model:latest"]})',context);
  assert.equal(select.value,'');
  assert.equal(select.options.length,2);
  context.FormData = function(form) { return Object.entries(form.values); };
  context.settingsForm = {values:{local_model:'qwen3-vl:latest',india_enabled:'true',bangladesh_enabled:'true',
    scan_interval_seconds:'5',vision_output_tokens:'4096',vision_context_tokens:'8192',vision_timeout_seconds:'7200',
    incoming_dir:'old-bd-input',output_dir:'old-bd-output',india_incoming_dir:'old-india-input',india_output_dir:'old-india-output'},
    querySelector:selector=>({value:selector.includes('incoming') ? 'C:\\PDF inbox\\' : 'C:\\Invoices\\'})};
  let changes = vm.runInContext('settingsChanges(settingsForm)',context);
  assert.equal(changes.incoming_dir,'C:\\PDF inbox/bangladesh');
  assert.equal(changes.india_incoming_dir,'C:\\PDF inbox/india');
  assert.equal(changes.output_dir,'C:\\Invoices/bangladesh');
  assert.equal(changes.india_output_dir,'C:\\Invoices/india');
  assert.equal(changes.india_enabled,true);
  assert.equal(changes.vision_timeout_seconds,7200);
  context.settingsForm.querySelector=()=>({value:''});
  changes=vm.runInContext('settingsChanges(settingsForm)',context);
  assert.equal(changes.incoming_dir,'old-bd-input');
  assert.equal(changes.india_incoming_dir,'old-india-input');
  assert.equal(changes.bangladesh_enabled,true);
  assert.equal(changes.jordan_enabled,false);
  assert.equal(Object.keys(changes).length,12);
  context.intakeBadge = {textContent:'',className:''};
  context.document.querySelector = () => context.intakeBadge;
  context.intakeControl = {value:'false',dataset:{intakeControl:'bangladesh',current:'true'}};
  vm.runInContext('updateIntakeStatus(intakeControl)',context);
  assert.equal(context.intakeBadge.textContent,'Disabled · unsaved');
  assert.equal(context.intakeBadge.className,'badge');
  context.intakeControl.value='true';
  vm.runInContext('updateIntakeStatus(intakeControl)',context);
  assert.equal(context.intakeBadge.textContent,'Enabled');
  console.log('Dashboard status and shared-folder settings passed.');
}
check().catch(error=>{console.error(error);process.exitCode=1;});
