/* Session-only credentials; all library text is rendered as text, not HTML. */
const $ = id => document.getElementById(id);
const words = {
  library:['Library','Bibliothek'],signin:['Sign in','Anmelden'],key:['Library access key','Bibliotheks-Zugangsschlüssel'],connect:['Connect','Verbinden'],
  songs:['Songs','Songs'],outputs:['Downloads','Downloads'],jobs:['Jobs','Aufträge'],devices:['Devices','Geräte'],import:['Import song','Song hinzufügen'],
  artist:['Artist','Interpret'],title:['Title','Titel'],packages:['Packages','Pakete'],empty:['No songs yet.','Noch keine Songs vorhanden.'],select:['Select a song','Song auswählen'],
  save:['Save','Speichern'],cover:['Cover','Cover'],audio:['Audio','Audio'],video:['Video','Video'],export:['Export','Export'],remove:['Remove project','Projekt entfernen'],
  type:['Type','Typ'],size:['Size','Größe'],state:['State','Status'],progress:['Progress','Fortschritt'],device:['Device','Gerät'],pair:['Pair device','Gerät koppeln'],
  noencoder:['Media conversion is not available on this server.','Medienkonvertierung ist auf diesem Server noch nicht verfügbar.'],
  local:['Private library · Home network · No analytics','Private Bibliothek · Heimnetz · Keine Analyse'],
  search:['Search songs and artists','Songs und Interpreten suchen'],download:['Download','Herunterladen'],revoke:['Revoke','Trennen'],
  active:['Active','Aktiv'],revoked:['Revoked','Getrennt'],notes:['Notes','Noten'],media:['Media','Medien'],missing:['Not stored','Nicht vorhanden'],
  imported:['Song imported','Song hinzugefügt'],saved:['Saved as a new project version','Als neuer Projektstand gespeichert'],queued:['Job queued','Auftrag gestartet'],
  confirm:['Remove this project snapshot? Shared media and already built DLCs will be retained.','Diesen Projektstand entfernen? Gemeinsame Medien und bereits gebaute DLCs bleiben erhalten.'],
  uploading:['Uploading…','Wird hochgeladen …'],working:['Working…','Wird verarbeitet …'],pairing:['Pairing code (valid for 5 minutes, one device):','Kopplungscode (5 Minuten gültig, ein Gerät):'],
  fingerprint:['Certificate SHA-256','Zertifikat SHA-256'],tooLarge:['Use a song file up to 16 MiB.','Eine Songdatei bis 16 MiB verwenden.'],
  language:['Language','Sprache'],theme:['Switch dark/light mode','Dunklen/hellen Modus wechseln'],logout:['Sign out','Abmelden'],refresh:['Refresh','Aktualisieren'],
  project:['Project','Projekt'],community:['Community song','Community-Song'],ultrastar:['UltraStar','UltraStar'],midi:['MIDI','MIDI'],lrc:['LRC','LRC'],
  pack:['Song pack','Songpack'],package:['Package','Paket'],readyDlc:['Ready DLC','Fertiges DLC'],
  downloadDlc:['Download DLC','DLC herunterladen'],downloadPack:['Download song pack','Songpack herunterladen'],
  xboxFolder:['Xbox destination','Xbox-Zielordner'],dlcImported:['DLC added to songs','DLC zur Songübersicht hinzugefügt']
};
let lang = localStorage.getItem('openlips-library-language') || (navigator.language.startsWith('de') ? 'de' : 'en');
let token = '', catalog = {projects:[],packages:[],artifacts:[],songs:[]}, selected = null, selectedSong = null, details = null, identity = {}, poll = null, coverURL = null, mediaField = '';
const t = key => (words[key] || [key,key])[lang === 'de' ? 1 : 0];
const kindName = value => ({chart:'.ols',midi:'MIDI',lrc:'LRC',dlc:'DLC'}[value] || value);
const stateName = value => ({queued:['Queued','Wartend'],running:['Processing','In Arbeit'],ready:['Ready','Fertig'],failed:['Failed','Fehlgeschlagen']}[value] || [value,value])[lang==='de'?1:0];
function language() {
  document.documentElement.lang = lang; $('language').value = lang;
  document.querySelectorAll('[data-i18n]').forEach(node => node.textContent = t(node.dataset.i18n));
  $('search').placeholder = t('search');
  for (const id of ['theme','logout','refresh']) $(id).title = t(id);
  icons(); if (token || identity.auth_required===false) renderSongs();
  $('import-dlc').title=t('readyDlc'); $('import-dlc').setAttribute('aria-label',t('readyDlc'));
}
function icons() { if (window.lucide) window.lucide.createIcons(); }
function message(text) { $('status').textContent = text || ''; }
function el(tag, text, attrs = {}) { const node = document.createElement(tag); if(text !== null) node.textContent = text; for(const [key,value] of Object.entries(attrs)) node.setAttribute(key,value); return node; }
function action(icon, label, callback) { const button = el('button',null,{title:label}); button.append(el('i',null,{'data-lucide':icon})); if(label) button.append(el('span',label)); button.addEventListener('click',()=>run(callback)); return button; }
async function api(path, options = {}) {
  const headers = {...(token ? {Authorization:'Bearer ' + token} : {}), ...(options.headers || {})};
  if (options.json !== undefined) { options.body = JSON.stringify(options.json); headers['Content-Type'] = 'application/json'; }
  const response = await fetch('/api/v1/' + path, {...options,headers,credentials:'omit',cache:'no-store'});
  if (!response.ok) { const data = await response.json().catch(()=>({})); throw new Error(data.error || `Request failed (${response.status})`); }
  return options.binary ? response.blob() : response.json();
}
async function run(callback) { try { await callback(); } catch(error) { message(error.message); } }
async function refresh() {
  catalog = await api('library'); $('counts').textContent = `${catalog.songs.length} ${t('songs')} · ${catalog.packages.length} DLC`;
  renderSongs(); renderOutputs(); await jobs();
}
function renderSongs() {
  const query = $('search').value.toLocaleLowerCase(); $('song-rows').replaceChildren();
  const records = catalog.songs.filter(p=>(p.artist+' '+p.title+' '+(p.package_title || '')).toLocaleLowerCase().includes(query));
  $('empty-songs').hidden = records.length > 0;
  for (const song of records) {
    const row = el('tr',null,{'data-id':song.key,tabindex:'0'}); if (song.key === selectedSong) row.className='selected';
    const label = song.kind==='dlc' ? 'DLC' + (song.song_count>1 ? ' · '+t('pack') : '') : t(song.kind);
    for(const value of [song.artist,song.title,label]) row.append(el('td',value));
    row.addEventListener('click',()=>run(()=>selectSong(song.key)));
    row.addEventListener('keydown',event=>{if(event.key==='Enter') run(()=>selectSong(song.key));});
    $('song-rows').append(row);
  }
}
async function selectSong(key) {
  const song = catalog.songs.find(p=>p.key===key); if(!song)return;
  if(song.project_id)return select(song.project_id);
  selected=null; selectedSong=key; details=null; renderSongs();
  $('song-controls').hidden=true; $('package-controls').hidden=false;
  $('song-title').textContent=song.title; $('song-artist').textContent=song.artist;
  if(coverURL)URL.revokeObjectURL(coverURL); coverURL=null; $('cover').src='/logo-light.png';
  $('package-info').replaceChildren();
  for(const [label,value] of [[t('type'),t('readyDlc')],[t('package'),song.package_title],
      [t('songs'),song.song_count],[t('size'),(song.bytes/1048576).toFixed(1)+' MiB'],
      [t('xboxFolder'),'Content/0000000000000000/4D530888/00000002']])
    $('package-info').append(el('dt',label),el('dd',String(value)));
  const button=$('download-package'); button.replaceChildren(el('i',null,{'data-lucide':'download'}),
      el('span',t(song.song_count>1?'downloadPack':'downloadDlc')));
  icons();
}
async function select(id) {
  selected = id; selectedSong='project:'+id; details = await api('projects/' + id); renderSongs();
  $('package-controls').hidden=true;
  const p = details.project; $('song-title').textContent = p.title; $('song-artist').textContent = p.artist;
  for(const kind of ['chart','midi']) document.querySelector(`[data-job="${kind}"]`).disabled=p.notes.some(note=>!note.pitch_assigned);
  document.querySelector('[data-job="chart"]').disabled ||= p.notes.some(note=>!note.text.trim());
  $('edit-title').value=p.title; $('edit-artist').value=p.artist; $('song-controls').hidden=false;
  $('song-info').replaceChildren();
  for (const [label,value] of [[t('notes'),p.notes.length],['BPM',p.bpm],[t('audio'),details.media.audio ? details.media.audio.filename.split('.').pop() : t('missing')],[t('video'),details.media.video ? details.media.video.filename.split('.').pop() : t('missing')]]) {
    $('song-info').append(el('dt',label),el('dd',String(value)));
  }
  if(coverURL) URL.revokeObjectURL(coverURL); coverURL=null; $('cover').src='/logo-light.png';
  if(details.media.cover) { coverURL=URL.createObjectURL(await api(`projects/${id}/media/cover`,{binary:true})); $('cover').src=coverURL; }
}
async function download(path, name) {
  if(identity.auth_required===false) { el('a',null,{href:'/api/v1/'+path,download:name}).click(); return; }
  const blob=await api(path,{binary:true}); const url=URL.createObjectURL(blob); const link=el('a',null,{href:url,download:name}); link.click(); setTimeout(()=>URL.revokeObjectURL(url),1000);
}
function renderOutputs() {
  $('output-rows').replaceChildren();
  for(const record of [...catalog.packages.map(p=>({...p,kind:'DLC',endpoint:'packages'})),...catalog.artifacts.map(a=>({...a,title:catalog.projects.find(p=>p.id===a.project_id)?.title || a.filename,endpoint:'artifacts'}))]) {
    const row=el('tr',null); for(const value of [record.title,kindName(record.kind),`${(record.bytes/1048576).toFixed(1)} MiB`]) row.append(el('td',value));
    const cell=el('td',null); const button=action('download','',()=>download(`${record.endpoint}/${record.id}`,record.filename)); button.title=t('download');button.setAttribute('aria-label',t('download'));cell.append(button); row.append(cell); $('output-rows').append(row);
  } icons();
}
async function jobs() {
  if(!token && identity.auth_required!==false) return;
  const data=await api('jobs'); $('job-rows').replaceChildren();
  for(const job of data.jobs) { const row=el('tr',null); for(const value of [(job.title || job.id.slice(0,8))+' · '+kindName(job.kind || 'DLC'),stateName(job.state),job.progress]) row.append(el('td',value)); $('job-rows').append(row); }
}
async function devices() {
  const data=await api('devices'); $('device-rows').replaceChildren();
  $('fingerprint').textContent=identity.fingerprint ? `${t('fingerprint')}: ${identity.fingerprint}` : '';
  for(const device of data.devices) { const row=el('tr',null); row.append(el('td',device.name),el('td',t(device.revoked?'revoked':'active')));
    const cell=el('td',null); if(!device.revoked) cell.append(action('unlink',t('revoke'),async()=>{await api('devices/'+device.id,{method:'DELETE'});await devices();})); row.append(cell); $('device-rows').append(row); }
  icons();
}
async function enter() {
    const capability=await api('status'); identity=await api('identity'); await refresh();
    $('signin').hidden=true; $('workspace').hidden=false; $('logout').hidden=identity.auth_required===false; $('library-name').textContent=identity.name;
    document.querySelector('[data-tab="devices"]').hidden=identity.auth_required===false;
    $('dlc').disabled=!capability.encoding; $('codec-note').hidden=capability.encoding; $('pair').disabled=!identity.pairing;
    if(poll) clearInterval(poll); poll=setInterval(()=>run(async()=>{await jobs();if(!$('outputs-view').hidden){catalog=await api('library');renderOutputs();}}),3000);message('');
}
$('login-form').addEventListener('submit',event=>{event.preventDefault(); run(async()=>{
  token=$('access-key').value.trim(); $('access-key').value='';
  try { await enter(); } catch(error) {token='';throw error;}
});});
$('logout').addEventListener('click',()=>{token='';if(poll)clearInterval(poll);poll=null;$('workspace').hidden=true;$('signin').hidden=false;$('logout').hidden=true;selected=null;selectedSong=null;details=null;catalog={projects:[],packages:[],artifacts:[],songs:[]};$('pair-code').textContent='';$('pair-code').hidden=true;if(coverURL)URL.revokeObjectURL(coverURL);message('');});
$('language').addEventListener('change',()=>{lang=$('language').value;localStorage.setItem('openlips-library-language',lang);language();if(selectedSong)run(()=>selectSong(selectedSong));});
document.documentElement.dataset.theme=localStorage.getItem('openlips-library-theme') || (matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light');
$('theme').addEventListener('click',()=>{const value=document.documentElement.dataset.theme==='dark'?'light':'dark';document.documentElement.dataset.theme=value;localStorage.setItem('openlips-library-theme',value);});
$('refresh').addEventListener('click',()=>run(refresh)); $('search').addEventListener('input',renderSongs);
document.querySelectorAll('[data-tab]').forEach(button=>button.addEventListener('click',()=>{document.querySelectorAll('[data-tab]').forEach(b=>b.classList.toggle('active',b===button));for(const name of ['songs','outputs','jobs','devices']) $(name+'-view').hidden=name!==button.dataset.tab;if(button.dataset.tab==='devices')run(devices);if(button.dataset.tab==='outputs')run(refresh);}));
$('import').addEventListener('click',()=>$('song-file').click());
$('import-dlc').addEventListener('click',()=>$('dlc-file').click());
$('dlc-file').addEventListener('change',()=>run(async()=>{const file=$('dlc-file').files[0];if(!file)return;message(t('uploading'));const result=await api('packages',{method:'POST',body:file,headers:{'Content-Type':'application/octet-stream'}});await refresh();const song=catalog.songs.find(p=>p.package_id===result.id);if(song)await selectSong(song.key);document.querySelector('[data-tab="songs"]').click();message(t('dlcImported'));$('dlc-file').value='';}));
$('download-package').addEventListener('click',()=>run(async()=>{const song=catalog.songs.find(p=>p.key===selectedSong);if(song?.package_id)await download('packages/'+song.package_id,song.filename);}));
$('song-file').addEventListener('change',()=>run(async()=>{const file=$('song-file').files[0];if(!file)return;if(file.size>16*1048576)throw new Error(t('tooLarge'));message(t('uploading'));
  const bytes=new Uint8Array(await file.arrayBuffer());let binary='';for(let n=0;n<bytes.length;n+=8192)binary+=String.fromCharCode(...bytes.subarray(n,n+8192));
  const result=await api('import',{method:'POST',json:{name:file.name,data:btoa(binary)}});await refresh();await select(result.id);message(t('imported'));$('song-file').value='';
}));
$('save-meta').addEventListener('click',()=>run(async()=>{if(!selected)return;const result=await api('projects/'+selected,{method:'POST',json:{title:$('edit-title').value,artist:$('edit-artist').value}});await refresh();await select(result.id);message(t('saved'));}));
document.querySelectorAll('[data-media]').forEach(button=>button.addEventListener('click',()=>{mediaField=button.dataset.media;$('media-file').accept=mediaField==='cover'?'.png,.jpg,.jpeg,.webp':mediaField==='audio'?'.mp3,.wav,.flac,.m4a,.aac,.ogg,.opus,.wma':'.mp4,.mkv,.webm,.mov,.avi,.wmv';$('media-file').click();}));
$('media-file').addEventListener('change',()=>run(async()=>{const file=$('media-file').files[0];if(!file||!selected)return;message(t('uploading'));const ext=file.name.slice(file.name.lastIndexOf('.')).toLowerCase();const result=await api(`projects/${selected}/media/${mediaField}`,{method:'POST',body:file,headers:{'X-File-Name':'media'+ext,'Content-Type':'application/octet-stream'}});await refresh();await select(result.id);message(t('saved'));$('media-file').value='';}));
const lyricButton=action('captions','LRC',()=>$('lyric-file').click());document.querySelector('.media-actions').append(lyricButton);
$('lyric-file').addEventListener('change',()=>run(async()=>{const file=$('lyric-file').files[0];if(!file||!selected)return;if(file.size>2*1048576)throw new Error(t('tooLarge'));const text=await file.text();const bytes=new TextEncoder().encode(text);let binary='';for(let n=0;n<bytes.length;n+=8192)binary+=String.fromCharCode(...bytes.subarray(n,n+8192));const result=await api(`projects/${selected}/lyrics`,{method:'POST',json:{data:btoa(binary)}});await refresh();await select(result.id);message(t('saved'));$('lyric-file').value='';}));
document.querySelectorAll('[data-job]').forEach(button=>button.addEventListener('click',()=>run(async()=>{if(!selected)return;await api('jobs',{method:'POST',json:{projects:[selected],kind:button.dataset.job}});await jobs();message(t('queued'));})));
$('remove').addEventListener('click',()=>run(async()=>{if(!selected||!confirm(t('confirm')))return;await api('projects/'+selected,{method:'DELETE'});selected=null;selectedSong=null;details=null;$('song-controls').hidden=true;$('song-title').textContent=t('select');$('song-artist').textContent='';await refresh();message('');}));
$('pair').addEventListener('click',()=>run(async()=>{const result=await api('pairing',{method:'POST',json:{}});$('pair-code').textContent=t('pairing')+' '+result.code;$('pair-code').hidden=false;setTimeout(()=>{$('pair-code').hidden=true;$('pair-code').textContent='';},result.expires_in*1000);}));
language();
run(async()=>{identity=await api('identity');if(identity.auth_required===false)await enter();else $('signin').hidden=false;});
