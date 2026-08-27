let state = null;
let currentProject = null;
let currentJob = null;
let renderUploadName = null;
let pollTimer = null;

const $ = (id) => document.getElementById(id);

async function api(url, options={}) {
  const res = await fetch(url, options);
  if (!res.ok) {
    let msg = await res.text();
    try { msg = JSON.parse(msg).detail || msg; } catch {}
    throw new Error(msg);
  }
  return res.json();
}

function fmtMin(sec){ return (sec/60).toFixed(1); }

async function refresh(){
  state = await api('/api/state');
  renderEnv();
  renderProjects();
  if(currentProject){
    const found = state.projects.find(p => p.slug === currentProject);
    if(found) renderProject(found);
  }
}

function renderEnv(){
  const e = state.environment;
  const gpu = e.gpu && e.gpu.length ? e.gpu.join(', ') : 'CPU baseline';
  const health = e.ready ? 'READY' : `CHECK SETUP${e.issues && e.issues.length ? '<br>'+e.issues.join('<br>') : ''}`;
  $('env').innerHTML = `<b>Runtime · ${health}</b><br>Python ${e.python}<br>${e.machine || ''}<br>DDSP ${e.ddsp || 'missing'}<br>TensorFlow ${e.tensorflow || 'missing'}<br>${gpu}`;
}

function renderProjects(){
  const el = $('projectList'); el.innerHTML = '';
  state.projects.forEach(p => {
    const b = document.createElement('button');
    b.className = 'project' + (p.slug === currentProject ? ' active' : '');
    const stage = p.model_ready ? `checkpoint ${p.latest_step || 'ready'}` : p.dataset_ready ? 'data prepared · NOT TRAINED' : p.sources.files.length ? 'recordings added · data not prepared' : 'new model';
    b.innerHTML = `<strong>${p.name}</strong><br><small>${p.sources.total_duration_min.toFixed(1)} min · ${stage}</small>`;
    b.onclick = () => { currentProject = p.slug; renderProjects(); renderProject(p); };
    el.appendChild(b);
  });
  if(!currentProject && state.projects.length){
    currentProject = state.projects[0].slug;
    renderProjects();
    renderProject(state.projects[0]);
  }
}

function renderProject(p){
  $('title').textContent = p.name;
  $('subtitle').textContent = `voice model project · ${p.slug}`;

  const hasSources = p.sources.files.length > 0;
  const latestStep = Number(p.latest_step || 0);
  let status = 'ADD TRAINING RECORDINGS';
  let pillClass = 'pill';
  if(p.model_ready){ status = `MODEL READY · CHECKPOINT ${latestStep || ''}`.trim(); pillClass = 'pill good'; }
  else if(p.dataset_ready){ status = 'DATA READY · MODEL NOT TRAINED YET'; pillClass = 'pill warn'; }
  else if(hasSources){ status = 'RECORDINGS READY · PREPARE DATA NEXT'; }
  $('statusPill').textContent = status;
  $('statusPill').className = pillClass;

  const s = p.sources;
  $('minutes').textContent = s.total_duration_min.toFixed(1);
  $('fileCount').textContent = s.files.length;
  $('datasetGrade').textContent = s.total_duration_min >= 15 ? 'good' : s.total_duration_min >= 10 ? 'usable' : 'short';
  $('cov10').style.setProperty('--w', `${Math.min(100, s.total_duration_sec/600*100)}%`);
  $('cov15').style.setProperty('--w', `${Math.min(100, s.total_duration_sec/900*100)}%`);

  $('sourceList').innerHTML = s.files.map(f =>
    `<div class="source"><strong>${f.name}</strong><span>${f.error ? f.error : `${fmtMin(f.duration_sec)} min · ${f.sample_rate/1000} kHz · ${f.channels} ch · ${f.bit_depth} bit`}</span></div>`
  ).join('') || '<p class="muted">No WAVs yet.</p>';

  $('wfRecordings').className = 'workflow-step ' + (hasSources ? 'done' : 'current');
  $('wfDataset').className = 'workflow-step ' + (p.dataset_ready ? 'done' : hasSources ? 'current' : '');
  $('wfModel').className = 'workflow-step ' + (p.model_ready ? 'done' : p.dataset_ready ? 'current' : '');
  $('wfUse').className = 'workflow-step ' + (p.model_ready ? 'current' : '');

  $('prepareBtn').disabled = !hasSources;
  $('prepareBtn').textContent = p.dataset_ready ? 'REBUILD PREPARED DATASET' : 'STEP 2 · ANALYZE + PREPARE DATASET';
  $('prepareStatus').className = 'stage-status ' + (p.dataset_ready ? 'good' : '');
  $('prepareStatus').textContent = p.dataset_ready
    ? 'DATASET PREPARED ✓  This step is complete. The model is still separate: go to TRAIN MODEL to teach it your voice.'
    : hasSources ? 'Recordings are loaded. Next: analyze them and build the DDSP training dataset.' : 'Add training recordings first.';

  $('trainBtn').disabled = !p.dataset_ready;
  $('trainGate').className = 'explain-box ' + (p.dataset_ready ? (p.model_ready ? 'good' : 'warn') : '');
  if(!p.dataset_ready){
    $('trainGate').innerHTML = '<strong>Training cannot start yet.</strong><span>Go back to RECORDINGS + DATA and prepare the dataset first.</span>';
  } else if(p.model_ready){
    $('trainGate').innerHTML = `<strong>A trained checkpoint exists${latestStep ? ` at step ${latestStep.toLocaleString()}` : ''}.</strong><span>You can use it now, or resume training toward a higher target if you want.</span>`;
  } else {
    $('trainGate').innerHTML = '<strong>DATASET READY — MODEL NOT TRAINED YET.</strong><span>The preparation stage is finished. Press the button below to start the actual DDSP learning run.</span>';
  }
  const target = parseInt($('steps').value || '30000', 10);
  $('trainBtn').textContent = p.model_ready ? `RESUME TRAINING TO ${target.toLocaleString()} TOTAL STEPS` : `START MODEL TRAINING — ${target.toLocaleString()} STEPS`;

  $('renderBtn').disabled = !p.model_ready;
  $('renderGate').className = 'explain-box ' + (p.model_ready ? 'good' : 'warn');
  $('renderGate').innerHTML = p.model_ready
    ? `<strong>Model checkpoint ready${latestStep ? ` · step ${latestStep.toLocaleString()}` : ''}.</strong><span>You are no longer training here. Choose a new performance below and render it through the learned voice model.</span>`
    : '<strong>No trained checkpoint yet.</strong><span>Prepare data, then run TRAIN MODEL. Rendering becomes available as soon as a checkpoint exists.</span>';

  document.querySelector('[data-tab="render"]').disabled = !p.model_ready;
  document.querySelector('[data-tab="export"]').disabled = !p.model_ready;
  $('downloadModelBundle').classList.toggle('hidden', !p.model_ready);
  $('downloadModelBundle').href = `/api/projects/${p.slug}/model-bundle.zip`;
  $('downloadExport').classList.toggle('hidden', !p.export_ready);
  $('downloadExport').href = `/api/projects/${p.slug}/export.zip`;
  loadRenders();
  loadIncoming();
}
function requireProject(){
  if(!currentProject) throw new Error('Create or select a project first.');
  return currentProject;
}

function setTab(name){
  document.querySelectorAll('.tabs button').forEach(b => b.classList.toggle('active', b.dataset.tab === name));
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  $(`tab-${name}`).classList.add('active');
}

document.querySelectorAll('.tabs button').forEach(b => b.onclick = () => setTab(b.dataset.tab));

$('newProjectBtn').onclick = () => $('modal').classList.remove('hidden');
$('cancelModal').onclick = () => $('modal').classList.add('hidden');
$('createProject').onclick = async () => {
  try{
    const name = $('projectName').value.trim();
    const p = await api('/api/projects', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name})});
    currentProject = p.slug;
    $('modal').classList.add('hidden');
    $('projectName').value='';
    await refresh();
  }catch(e){alert(e.message)}
};

$('trainingFiles').onchange = async (ev) => {
  try{
    const slug = requireProject();
    const fd = new FormData();
    [...ev.target.files].forEach(f => fd.append('files', f));
    await api(`/api/projects/${slug}/upload`, {method:'POST',body:fd});
    ev.target.value='';
    await refresh();
  }catch(e){alert(e.message)}
};

$('prepareBtn').onclick = async () => {
  try{
    const project=requireProject();
    $('prepareBtn').disabled=true;
    $('prepareStatus').className='stage-status busy';
    $('prepareStatus').textContent='Preparing dataset… this analyzes your recordings. MODEL TRAINING HAS NOT STARTED.';
    const job=await api('/api/prepare',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({project})});
    watchJob(job.id, {onDone: async (j) => {
      if(j.status==='done'){
        $('prepareStatus').className='stage-status good';
        $('prepareStatus').textContent='DATASET PREPARED ✓  Next: TRAIN MODEL. No model training has happened yet.';
        await refresh();
        setTab('train');
      } else {
        $('prepareStatus').className='stage-status';
        $('prepareStatus').textContent='Dataset preparation failed. Open the preparation details above for the exact error.';
      }
    }});
  }catch(e){$('prepareBtn').disabled=false;alert(e.message)}
};

$('steps').oninput = () => {
  if(!currentProject || !state) return;
  const p=state.projects.find(x=>x.slug===currentProject);
  if(!p) return;
  const target=parseInt($('steps').value || '30000',10);
  $('trainBtn').textContent=p.model_ready ? `RESUME TRAINING TO ${target.toLocaleString()} TOTAL STEPS` : `START MODEL TRAINING — ${target.toLocaleString()} STEPS`;
};
$('trainBtn').onclick = async () => {
  try{
    const project=requireProject();
    const steps=parseInt($('steps').value,10);
    const batch_size=parseInt($('batch').value,10);
    $('logTitle').textContent='MODEL TRAINING LOG';
    $('log').textContent='Starting actual DDSP model training…';
    const job=await api('/api/train',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({project,steps,batch_size})});
    watchJob(job.id);
  }catch(e){alert(e.message)}
};

$('exportBtn').onclick = async () => {
  try{
    const project=requireProject();
    const job=await api('/api/export',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({project})});
    watchJob(job.id);
  }catch(e){alert(e.message)}
};

async function loadIncoming(){
  if(!currentProject)return;
  try{
    const items=await api(`/api/projects/${currentProject}/incoming`);
    const sel=$('incomingRender');
    sel.innerHTML='<option value="">Choose incoming Surfwave Studio take…</option>'+items.map(r=>`<option value="${r.name}">${r.name}</option>`).join('');
    if(renderUploadName && items.some(r=>r.name===renderUploadName)) sel.value=renderUploadName;
  }catch{}
}

$('incomingRender').onchange = (ev) => {
  const name=ev.target.value;
  if(!name)return;
  renderUploadName=name;
  $('renderFileName').textContent=`incoming: ${name}`;
};

$('renderFile').onchange = async (ev) => {
  try{
    const slug=requireProject();
    const file=ev.target.files[0]; if(!file)return;
    const fd=new FormData(); fd.append('file',file);
    const r=await api(`/api/projects/${slug}/render-upload`,{method:'POST',body:fd});
    renderUploadName=r.filename;
    $('renderFileName').textContent=file.name;
    await loadIncoming();
    $('incomingRender').value=r.filename;
  }catch(e){alert(e.message)}
};

function bindRange(id, out, fn){
  $(id).oninput = () => $(out).textContent = fn($(id).value);
}
bindRange('pitch','pitchVal',v=>`${v} st`);
bindRange('harmonic','harmVal',v=>`${v}%`);
bindRange('noise','noiseVal',v=>`${v}%`);

$('renderBtn').onclick = async () => {
  try{
    const project=requireProject();
    if(!renderUploadName) throw new Error('Choose a render source WAV first.');
    const body={
      project,
      filename:renderUploadName,
      pitch_semitones:parseFloat($('pitch').value),
      harmonic_gain:parseFloat($('harmonic').value)/100,
      noise_gain:parseFloat($('noise').value)/100,
      reverb:$('reverb').checked
    };
    const job=await api('/api/render',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    watchJob(job.id);
  }catch(e){alert(e.message)}
};

$('stopBtn').onclick = async () => {
  if(currentJob) await api(`/api/jobs/${currentJob}/stop`,{method:'POST'});
};

function watchJob(id, options={}){
  currentJob=id;
  if(pollTimer) clearInterval(pollTimer);
  const poll=async()=>{
    try{
      const j=await api(`/api/jobs/${id}`);
      const text=j.log || `${j.kind}: ${j.status}`;
      if(j.kind==='prepare'){
        $('prepareLog').textContent=text;
        $('prepareLog').scrollTop=$('prepareLog').scrollHeight;
      } else {
        $('log').textContent=text;
        $('log').scrollTop=$('log').scrollHeight;
      }
      if(['done','failed'].includes(j.status)){
        clearInterval(pollTimer); pollTimer=null; currentJob=null;
        await refresh(); await loadRenders();
        if(options.onDone) await options.onDone(j);
      }
    }catch(e){ console.error(e); }
  };
  poll(); pollTimer=setInterval(poll,1200);
}
async function loadRenders(){
  if(!currentProject)return;
  try{
    const items=await api(`/api/projects/${currentProject}/renders`);
    $('renderList').innerHTML=items.map(r=>`
      <div class="render">
        <strong>${r.name}</strong>
        <audio controls src="/api/projects/${currentProject}/renders/${encodeURIComponent(r.name)}"></audio>
        <a href="/api/projects/${currentProject}/renders/${encodeURIComponent(r.name)}" download>save WAV</a>
      </div>`).join('') || '<p class="muted">No renders yet.</p>';
  }catch{}
}

refresh().catch(e=>alert(e.message));
