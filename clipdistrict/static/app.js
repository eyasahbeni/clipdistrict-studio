'use strict';
const $ = (id) => document.getElementById(id);
let CSRF = '', currentVideo = '', selectedExport = '';
let videoItems = [], outputItems = [], lastJobStates = new Map();

function toast(message, error = false) {
  const root = $('alert'); root.textContent = '';
  const child = document.createElement('div');
  child.className = `toast ${error ? 'error' : 'success'}`;
  child.textContent = message; root.appendChild(child);
  window.setTimeout(() => { if (root.contains(child)) child.remove(); }, 9000);
}
async function api(path, method = 'GET', body = undefined) {
  const init = {method, headers: {}};
  if (method !== 'GET') init.headers['X-ClipDistrict-Token'] = CSRF;
  if (body !== undefined) {
    init.headers['Content-Type'] = 'application/json'; init.body = JSON.stringify(body);
  }
  const response = await fetch(path, init);
  let payload;
  try { payload = await response.json(); } catch (_) { throw new Error('Server returned an invalid response'); }
  if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
  return payload;
}
async function request(action) {
  try { await action(); } catch (e) { toast(e.message, true); }
}
function showTab(name) {
  document.querySelectorAll('.page').forEach(p => p.classList.toggle('active', p.id === 'page-' + name));
  document.querySelectorAll('.nav button').forEach(b => b.classList.toggle('selected', b.dataset.tab === name));
  if (name === 'exports') refreshExports();
  if (name === 'studio') refreshVideos();
  if (name === 'settings') refreshStatus();
  document.querySelector('main').scrollTo?.(0, 0); window.scrollTo(0, 0);
}
function durationFmt(v) {
  const m = Math.floor(Number(v || 0) / 60);
  const s = Math.floor(Number(v || 0) % 60);
  return `${m}:${String(s).padStart(2, '0')}`;
}
function bytesFmt(n) {
  if (n > 1e9) return `${(n / 1e9).toFixed(2)} GB`;
  if (n > 1e6) return `${(n / 1e6).toFixed(1)} MB`;
  return `${Math.ceil(n / 1e3)} KB`;
}
function node(tag, text = '', className = '') {
  const e = document.createElement(tag);
  if (text) e.textContent = text;
  if (className) e.className = className;
  return e;
}
async function refreshStatus() {
  const status = await api('/api/status'); CSRF = status.token;
  $('server-state').textContent = '● ' + (status.ffmpeg ? 'Ready to render' : 'FFmpeg needed');
  $('server-state').style.color = status.ffmpeg ? '#89b8a1' : '#f4ad6b';
  const root = $('system-check'); root.textContent = '';
  [
    [status.ffmpeg, 'FFmpeg + FFprobe'],
    [status.api_key, 'YouTube search API key'],
    [status.whisper_installed, 'faster-whisper transcription package (optional)'],
    [status.oauth_ready, 'Google OAuth Desktop client (optional)']
  ].forEach(([ready, label]) => root.appendChild(node('div', `${ready ? '✓' : '○'} ${label}`)));
  $('oauth-state').textContent = status.oauth_ready ? '✓ OAuth Desktop client loaded' : 'Not configured';
  $('workspace-path').textContent = 'Local files folder: ' + status.workspace;
  $('search-hint').textContent = status.api_key ? 'Public metadata only. To make a Short, get permission and source footage from its creator.' :
    'To search here, add a YouTube Data API key in Settings. You can also browse YouTube in another tab.';
}
async function doSearch() {
  const query = $('search-query').value.trim();
  if (!query) throw new Error('Enter a search query');
  const result = $('search-results');
  result.replaceChildren(node('div', 'Searching public YouTube metadata...', 'empty'));
  const data = await api('/api/search?q=' + encodeURIComponent(query) + '&live=' + ($('live-only').checked ? 'true' : 'false'));
  result.replaceChildren();
  if (!data.items.length) {
    result.appendChild(node('div', 'No matching videos. Try another search.', 'empty')); return;
  }
  data.items.forEach((item) => {
    const card = node('article', '', 'video-card');
    const img = node('img'); img.loading = 'lazy'; img.referrerPolicy = 'no-referrer';
    if (item.thumbnail && /^https:\/\/(i\.)?ytimg\.com\//.test(item.thumbnail)) img.src = item.thumbnail;
    img.alt = 'YouTube thumbnail'; card.appendChild(img);
    const body = node('div', '', 'body');
    body.appendChild(node('h3', item.title)); body.appendChild(node('p', item.creator));
    const actions = node('div', '', 'actions');
    const link = node('a', 'Open on YouTube ↗'); link.target = '_blank'; link.rel = 'noopener noreferrer';
    link.href = `https://www.youtube.com/watch?v=${encodeURIComponent(item.id)}`;
    actions.appendChild(link);
    const inspect = node('button', 'Inspect metadata');
    inspect.addEventListener('click', () => request(async () => {
      const meta = await api('/api/inspect?url=' + encodeURIComponent(item.url));
      toast(`${meta.title} · ${meta.creator} · ${meta.duration} — footage is not downloaded`);
    }));
    actions.appendChild(inspect); body.appendChild(actions); card.appendChild(body); result.appendChild(card);
  });
}
async function uploadRaw(path, file, label = 'Uploading') {
  if (!CSRF) await refreshStatus();
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest(); xhr.open('POST', path);
    xhr.setRequestHeader('X-ClipDistrict-Token', CSRF);
    xhr.setRequestHeader('X-Filename', file.name);
    xhr.setRequestHeader('Content-Type', 'application/octet-stream');
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) $('upload-progress').textContent = `${label}: ${Math.round(100 * event.loaded / event.total)}%`;
    };
    xhr.onerror = () => reject(new Error('Local upload failed'));
    xhr.onload = () => {
      let data = {};
      try { data = JSON.parse(xhr.responseText); } catch (_) {}
      if (xhr.status >= 200 && xhr.status < 300) resolve(data);
      else reject(new Error(data.error || 'Upload was rejected'));
    };
    xhr.send(file);
  });
}
async function importVideo(file) {
  if (!file) return;
  if (!/\.(mp4|mov|mkv|webm)$/i.test(file.name)) throw new Error('Use MP4, MOV, MKV or WEBM');
  if (file.size > 2 * 1024 ** 3) throw new Error('File exceeds 2 GB');
  $('upload-progress').textContent = 'Preparing local import...';
  const data = await uploadRaw('/api/import', file);
  $('upload-progress').textContent = '✓ File imported locally';
  await refreshVideos(data.video_id);
  toast('Video imported. Now select clip times, add captions, and render.');
}
async function refreshVideos(selectId = currentVideo) {
  const data = await api('/api/videos'); videoItems = data.items;
  const select = $('videos'); select.replaceChildren();
  select.appendChild(new Option(data.items.length ? 'Choose a video' : 'No videos imported', ''));
  data.items.forEach((v) => select.appendChild(new Option(`${v.id.slice(0,8)}... (${bytesFmt(v.size)})${v.subtitle ? ' • SRT' : ''}`, v.id)));
  if (selectId && data.items.some(v => v.id === selectId)) { select.value = selectId; changeVideo(selectId); }
}
function changeVideo(id) {
  currentVideo = id;
  const preview = $('local-preview');
  if (!id) { preview.pause(); preview.removeAttribute('src'); preview.load(); preview.style.display = 'none'; $('video-info').textContent = ''; return; }
  preview.src = `/media/${id}`; preview.style.display = 'block';
  const found = videoItems.find(v => v.id === id);
  $('video-info').textContent = `Local source • ${found ? bytesFmt(found.size) : ''}. You control what gets exported.`;
  $('highlight-results').replaceChildren(node('div', 'Use Suggest highlights to scan the transcript.', 'empty-small'));
}
async function addSubtitle(file) {
  if (!currentVideo) throw new Error('Choose a video first');
  if (!file || !/\.srt$/i.test(file.name)) throw new Error('Please choose an SRT subtitle file');
  const response = await uploadRaw(`/api/subtitles/${currentVideo}`, file, 'Importing subtitles');
  toast(`${response.cue_count} subtitle cues loaded.`);
  await refreshVideos(currentVideo);
}
async function getHighlights() {
  if (!currentVideo) throw new Error('Import/select a video first');
  const result = await api('/api/suggest', 'POST', {video_id: currentVideo, length: Number($('clip-duration').value) || 30, limit: 8});
  const root = $('highlight-results'); root.replaceChildren();
  if (!result.items.length) { root.appendChild(node('div', 'No matching GTA 6 signals. Choose timestamps manually.', 'empty-small')); return; }
  result.items.forEach((candidate) => {
    const btn = node('button', '', 'highlight-item');
    btn.appendChild(node('strong', `${durationFmt(candidate.start)} · Score ${candidate.score} · ${durationFmt(candidate.duration)} clip`));
    btn.appendChild(node('small', candidate.preview));
    btn.addEventListener('click', () => {
      $('clip-start').value = String(candidate.start); $('clip-duration').value = String(candidate.duration);
      const player = $('local-preview'); player.currentTime = candidate.start;
      toast('Highlight selected. Review the footage and click Generate.');
    });
    root.appendChild(btn);
  });
}
async function beginRender() {
  if (!currentVideo) throw new Error('Import/select a source video first');
  const data = await api('/api/render', 'POST', {
    video_id: currentVideo,
    start: Number($('clip-start').value), duration: Number($('clip-duration').value),
    style: $('caption-style').value, captions: $('burn-subs').checked
  });
  toast('Rendering started in the background. Open My Exports when complete.');
  await refreshJobs();
}
async function beginTranscribe() {
  if (!currentVideo) throw new Error('Import/select a source video first');
  const permit = $('download-model').checked;
  if (permit && !window.confirm('Download a free local Whisper model? Model weights are downloaded only with your approval.')) return;
  const data = await api('/api/transcribe', 'POST', {video_id: currentVideo, model: 'tiny', download_model: permit});
  toast('Transcription job started. It can take several minutes on CPU.');
  await refreshJobs();
}
async function refreshJobs() {
  const jobs = await api('/api/jobs');
  const root = $('jobs-panel'); root.replaceChildren();
  jobs.items.slice(-5).reverse().forEach((job) => {
    const item = node('div', `${job.kind.toUpperCase()} · ${job.state.toUpperCase()} — ${job.message}`, `job ${job.state}`);
    root.appendChild(item);
    const old = lastJobStates.get(job.id);
    if (old && old !== job.state && (job.state === 'done' || job.state === 'error')) {
      toast(`${job.kind}: ${job.state === 'done' ? 'completed' : job.message}`, job.state === 'error');
      if (job.kind === 'render' && job.state === 'done') refreshExports();
      if (job.kind === 'transcribe' && job.state === 'done') refreshVideos(currentVideo);
    }
    lastJobStates.set(job.id, job.state);
  });
}
async function refreshExports() {
  const data = await api('/api/exports'); outputItems = data.items;
  const root = $('export-results'); root.replaceChildren();
  const select = $('upload-selection');
  select.replaceChildren(new Option('Select exported Short', ''));
  if (!data.items.length) { root.appendChild(node('div', 'Your rendered Shorts will appear here.', 'empty')); return; }
  data.items.forEach((item) => {
    select.appendChild(new Option(`${item.id.slice(0,12)}... (${bytesFmt(item.size)})`, item.id));
    const card = node('article', '', 'export-card');
    const player = node('video'); player.controls = true; player.preload = 'metadata';
    player.src = `/output/${item.id}`; card.appendChild(player);
    card.appendChild(node('p', `Clip ${item.id.slice(0,8)} · ${bytesFmt(item.size)}`));
    const a = node('a', '↓ Download MP4'); a.href = `/output/${item.id}?download=1`; card.appendChild(a);
    const choose = node('button', '  Select for YouTube', 'button outline');
    choose.style.marginLeft = '7px'; choose.style.marginTop = '8px';
    choose.addEventListener('click', () => { selectedExport = item.id; select.value = item.id; toast('Select title and review upload settings below.'); });
    card.appendChild(choose); root.appendChild(card);
  });
  if (selectedExport && data.items.some(i => i.id === selectedExport)) select.value = selectedExport;
}
async function startYouTubeUpload() {
  const outputId = $('upload-selection').value;
  if (!outputId) throw new Error('Select an exported Short');
  if (!$('rights-confirmed').checked) throw new Error('Confirm publication rights first');
  const title = $('upload-title').value.trim();
  if (!title) throw new Error('Enter a title');
  if (!window.confirm(`Upload "${title}" to YouTube as PRIVATE using your signed-in channel?`)) return;
  const confirmation = window.prompt('Type UPLOAD PRIVATE to authorize the upload:');
  if (confirmation !== 'UPLOAD PRIVATE') return;
  const data = await api('/api/upload', 'POST', {
    output_id: outputId, title, description: $('upload-desc').value, audience: $('upload-audience').value,
    rights_confirmed: true, confirm: confirmation
  });
  toast('Upload job started. Google sign-in may open in your browser.'); await refreshJobs();
}
async function saveApiKey() {
  const key = $('api-key').value.trim();
  await api('/api/settings', 'POST', {api_key: key}); $('api-key').value = '';
  await refreshStatus(); toast(key ? 'YouTube API key is active in memory for this session.' : 'API key cleared.');
}
async function importOAuth(file) {
  if (!file) return;
  if (!file.name.toLowerCase().endsWith('.json')) throw new Error('Expected OAuth Desktop client JSON');
  await uploadRaw('/api/oauth-client', file, 'Reading OAuth desktop client');
  await refreshStatus(); toast('OAuth Desktop credentials stored in your local application data folder.');
}

function previewYouTubeLink() {
  const raw = $('video-url').value.trim();
  let url;
  try { url = new URL(raw); } catch (_) { throw new Error('Please enter a YouTube URL'); }
  if (url.protocol !== 'https:' || !['youtube.com','www.youtube.com','m.youtube.com','youtu.be'].includes(url.hostname)) {
    throw new Error('Only HTTPS YouTube links can be previewed');
  }
  let id = '';
  if (url.hostname === 'youtu.be') id = url.pathname.replace(/^\//,'').split('/')[0];
  else if (url.pathname === '/watch') id = url.searchParams.get('v') || '';
  else if (/^\/(shorts|live|embed)\//.test(url.pathname)) id = url.pathname.split('/')[2];
  if (!/^[A-Za-z0-9_-]{11}$/.test(id)) throw new Error('Invalid video URL');
  const root = $('youtube-embed'); root.replaceChildren();
  const frame = node('iframe'); frame.allow = 'accelerometer; autoplay; encrypted-media; gyroscope; picture-in-picture';
  frame.allowFullscreen = true; frame.referrerPolicy = 'no-referrer';
  frame.title = 'YouTube player'; frame.src = `https://www.youtube-nocookie.com/embed/${id}`;
  root.appendChild(frame);
  root.appendChild(node('p','Preview only. To create a Short, obtain the original video file from the creator or other authorized source.', 'hint'));
}

function wire() {
  document.querySelectorAll('.nav button').forEach(btn => btn.addEventListener('click', () => showTab(btn.dataset.tab)));
  $('hero-import').addEventListener('click', () => showTab('studio'));
  $('search-btn').addEventListener('click', () => request(doSearch));
  $('preview-youtube').addEventListener('click', () => request(previewYouTubeLink));
  $('search-query').addEventListener('keydown', (event) => { if (event.key === 'Enter') request(doSearch); });
  document.querySelectorAll('[data-q]').forEach(btn => btn.addEventListener('click', () => {
    $('search-query').value = btn.dataset.q; request(doSearch);
  }));
  $('choose-video').addEventListener('click', () => $('video-file').click());
  $('video-file').addEventListener('change', () => request(() => importVideo($('video-file').files[0])));
  const drop = $('drop-zone');
  drop.addEventListener('dragover', e => { e.preventDefault(); drop.classList.add('dragging'); });
  drop.addEventListener('dragleave', () => drop.classList.remove('dragging'));
  drop.addEventListener('drop', e => { e.preventDefault(); drop.classList.remove('dragging'); request(() => importVideo(e.dataTransfer.files[0])); });
  $('videos').addEventListener('change', e => changeVideo(e.target.value));
  $('import-srt').addEventListener('click', () => $('srt-file').click());
  $('srt-file').addEventListener('change', () => request(() => addSubtitle($('srt-file').files[0])));
  $('suggest-btn').addEventListener('click', () => request(getHighlights));
  $('transcribe-btn').addEventListener('click', () => request(beginTranscribe));
  $('render-btn').addEventListener('click', () => request(beginRender));
  $('refresh-exports').addEventListener('click', () => request(refreshExports));
  $('youtube-upload').addEventListener('click', () => request(startYouTubeUpload));
  $('upload-selection').addEventListener('change', e => selectedExport = e.target.value);
  $('save-api').addEventListener('click', () => request(saveApiKey));
  $('choose-oauth').addEventListener('click', () => $('oauth-file').click());
  $('oauth-file').addEventListener('change', () => request(() => importOAuth($('oauth-file').files[0])));
}
(async function init() {
  wire();
  try { await refreshStatus(); await refreshVideos(); await refreshExports(); await refreshJobs(); }
  catch (err) { toast('Local server connection failed: ' + err.message, true); }
  setInterval(() => request(refreshJobs), 2200);
})();
