'use strict';
const tickInput = document.getElementById('physical-tick');
const slider = document.getElementById('physical-slider');
const picture = document.getElementById('physical-image');
const status = document.getElementById('physical-status');
const previous = document.getElementById('previous-slice');
const next = document.getElementById('next-slice');
const limit = Number(document.body.dataset.ticks);
const job = document.body.dataset.job;
let tick = 0;
function showSlice(value) {
  const requested = Number(value);
  if (!Number.isInteger(requested) || requested < 0 || requested > limit) {
    tickInput.value = tick;
    return;
  }
  tick = requested;
  tickInput.value = slider.value = tick;
  previous.disabled = tick === 0;
  next.disabled = tick === limit;
  const url = `/api/jobs/${job}/physical-slice.svg?tick=${tick}`;
  picture.alt = `Physical qubit operations at circuit time slice ${tick}`;
  picture.src = url;
  document.getElementById('slice-download').href = url;
  status.textContent = `Circuit time slice ${tick} of ${limit}`;
}
picture.addEventListener('error', () => {
  status.textContent = 'This slice could not be displayed. Check that the compilation files are still available.';
});
previous.onclick = () => showSlice(tick - 1);
next.onclick = () => showSlice(tick + 1);
tickInput.onchange = () => showSlice(tickInput.value);
slider.oninput = () => showSlice(slider.value);
const viewport = document.getElementById('physical-viewport');
const zoomSlider = document.getElementById('physical-zoom');
const zoomLevel = document.getElementById('physical-zoom-level');
const zoomOut = document.getElementById('physical-zoom-out');
const zoomIn = document.getElementById('physical-zoom-in');
let magnification = 1;
let fitMode = true;
function applyZoom(value) {
  magnification = Math.max(.05, Math.min(4, value));
  if (!picture.naturalWidth || !picture.naturalHeight) return;
  picture.style.width = picture.naturalWidth * magnification + 'px';
  picture.style.height = picture.naturalHeight * magnification + 'px';
  zoomSlider.value = Math.round(magnification * 100);
  zoomLevel.textContent = Math.round(magnification * 100) + '%';
  zoomOut.disabled = magnification <= .05;
  zoomIn.disabled = magnification >= 4;
}
function fitDiagram() {
  fitMode = true;
  if (!picture.naturalWidth || !picture.naturalHeight) return;
  applyZoom(Math.min(1, (viewport.clientWidth - 32) / picture.naturalWidth,
    (viewport.clientHeight - 32) / picture.naturalHeight));
  viewport.scrollTop = viewport.scrollLeft = 0;
}
function changeZoom(value) {
  fitMode = false;
  applyZoom(value);
}
picture.addEventListener('load', () => {
  if (fitMode) fitDiagram();
  else applyZoom(magnification);
});
zoomOut.onclick = () => changeZoom(magnification / 1.2);
zoomIn.onclick = () => changeZoom(magnification * 1.2);
zoomSlider.oninput = () => changeZoom(Number(zoomSlider.value) / 100);
document.getElementById('physical-fit').onclick = fitDiagram;
document.getElementById('physical-actual-size').onclick = () => changeZoom(1);
viewport.addEventListener('wheel', event => {
  if (!event.ctrlKey && !event.metaKey) return;
  event.preventDefault();
  const delta = event.deltaY * (event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? viewport.clientHeight : 1);
  changeZoom(magnification * Math.exp(-Math.max(-100, Math.min(100, delta)) * .003));
}, {passive: false});
new ResizeObserver(() => { if (fitMode) fitDiagram(); }).observe(viewport);
showSlice(0);
