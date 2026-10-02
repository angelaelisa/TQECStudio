'use strict';
let simulationJob = null,
  simulationGeneration = null;

function sweepNumbers(id) {
  const text = $(id).value.trim();
  if (!text) throw Error('Enter scales and noise strengths.');
  return text.split(',').map(item => {
    if (!item.trim()) throw Error('Remove empty sweep values between commas.');
    const value = Number(item.trim());
    if (!Number.isFinite(value)) throw Error('Sweep values must be numbers separated by commas.');
    return value;
  });
}
window.updateSimulationContext = () => {
  $('sim-reference-control').hidden = $('noise-model').value !== 'custom';
};

function updateSweepSummary() {
  try {
    const count = sweepNumbers('sweep-ks').length * sweepNumbers('sweep-ps').length;
    $('sweep-summary').textContent = `${count} sampling points · up to ${(count*Number($('sim-shots').value)).toLocaleString()} total shots. Each point uses all selected observables.`;
  } catch (e) {
    $('sweep-summary').textContent = e.message;
  }
}
for (const id of ['sweep-ks', 'sweep-ps', 'sim-shots']) $(id).addEventListener('input', updateSweepSummary);
$('sim-zoom').onchange = () => {
  $('sim-zoom-controls').hidden = !$('sim-zoom').checked;
};
$('simulation-settings').onclick = () => panel('compile');
window.markSimulationStale = () => {
  if (simulationGeneration !== null) $('plot-provenance').textContent = 'The graph changed. These plots belong to the graph captured when this simulation started.';
};

function showSimulation(job, id) {
  $('plot-cards').replaceChildren();
  $('plot-empty').hidden = true;
  for (const plot of job.plots) {
    const article = document.createElement('article');
    article.className = 'plot-card';
    const heading = document.createElement('h3');
    heading.textContent = `Observable ${plot.observable}`;
    const image = document.createElement('img');
    image.src = `/api/simulations/${id}/${plot.png}`;
    image.alt = `Logical error probability per shot versus physical noise strength for observable ${plot.observable}`;
    article.append(heading, image);
    for (const ext of ['png', 'svg']) {
      const link = document.createElement('a');
      link.className = 'button';
      link.href = `/api/simulations/${id}/${plot[ext]}?download=1`;
      link.textContent = `Download ${ext.toUpperCase()}`;
      article.append(link);
    }
    const details = document.createElement('details');
    const summary = document.createElement('summary');
    summary.textContent = 'Show sampled counts and likelihood bounds';
    details.append(summary);
    const wrapper = document.createElement('div');
    wrapper.className = 'sample-table';
    const table = document.createElement('table');
    const head = document.createElement('tr');
    for (const label of ['k', 'p', 'Shots', 'Discards', 'Errors', 'Rate / shot', 'Lower bound', 'Upper bound']) {
      const th = document.createElement('th');
      th.textContent = label;
      head.append(th);
    }
    table.append(head);
    for (const row of job.rows.filter(r => r.observable === plot.observable)) {
      const tr = document.createElement('tr');
      for (const value of [row.k, row.p, row.shots, row.discards, row.errors, row.rate, row.likelihood_low, row.likelihood_high]) {
        const td = document.createElement('td');
        td.textContent = value === null ? '—' : Number.isInteger(value) ? String(value) : value.toPrecision(4);
        tr.append(td);
      }
      table.append(tr);
    }
    wrapper.append(table);
    details.append(wrapper);
    article.append(details);
    $('plot-cards').append(article);
  }
  $('simulation-downloads').hidden = false;
  $('simulation-csv').href = `/api/simulations/${id}/samples.csv`;
  $('simulation-record').href = `/api/simulations/${id}/simulation.json`;
}
$('simulate').onclick = async () => {
  if (simulationJob) return;
  $('simulate').disabled = true;
  try {
    const compilation = window.compilationSettings();
    if (compilation.observable_mode === 'selected' && !revision) {
      panel('surfaces');
      throw Error('Find and select correlation surfaces before simulating.');
    }
    const payload = {
      custom_reference_p: Number($('sim-reference').value),
      graph,
      revision: revision || (await api('/api/graph', graph)).revision,
      compilation,
      surfaces: [...$('surface-list').querySelectorAll('input:checked')].map(input => Number(input.value)),
      ks: sweepNumbers('sweep-ks'),
      ps: sweepNumbers('sweep-ps'),
      max_shots: Number($('sim-shots').value),
      max_errors: Number($('sim-errors').value),
      num_workers: Number($('sim-workers').value),
      decoder: $('sim-decoder').value,
      observable_inset: $('sim-inset').checked,
      zoom_bounds: $('sim-zoom').checked ? ['zoom-xmin', 'zoom-ymin', 'zoom-xmax', 'zoom-ymax'].map(id => Number($(id).value)) : null
    };
    const res = await api('/api/simulate', payload);
    simulationJob = res.id;
    simulationGeneration = generation;
    $('simulation-downloads').hidden = true;
    $('plot-cards').replaceChildren();
    $('plot-empty').hidden = false;
    $('plot-empty').textContent = 'Simulation in progress. Plots will appear when sampling finishes.';
    $('plot-provenance').textContent = `${compilation.convention.replaceAll('_',' ')} · ${compilation.noise_model.replaceAll('_',' ')} · k = ${payload.ks.join(', ')} · ${payload.ks.length*payload.ps.length} sampling points. Settings and graph captured for this run.`;
    const poll = async () => {
      try {
        const job = await api('/api/jobs/' + res.id);
        if (['queued', 'running'].includes(job.status)) {
          $('simulation-status').textContent = `${job.phase||'Queued'} · ${(job.sampled_shots||0).toLocaleString()} shots · ${(job.sampled_errors||0).toLocaleString()} errors across ${job.tasks} points`;
          setTimeout(poll, 1200);
          return;
        }
        simulationJob = null;
        $('simulate').disabled = false;
        if (job.status === 'failed') throw Error(job.error);
        showSimulation(job, res.id);
        $('simulation-status').textContent = 'Complete. Plots and sampled counts are ready.';
        if (simulationGeneration !== generation) window.markSimulationStale();
      } catch (error) {
        simulationJob = null;
        $('simulate').disabled = false;
        $('simulation-status').textContent = error.message;
        $('plot-empty').textContent = 'Simulation did not complete. Review the error and settings, then try again.';
      }
    };
    poll();
  } catch (error) {
    $('simulate').disabled = false;
    $('simulation-status').textContent = error.message;
  }
};
updateSweepSummary();
