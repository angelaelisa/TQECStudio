/* Form adapter for TQEC's public compilation settings. */
(() => {
  const el = id => document.getElementById(id);
  const channels = ['DEPOLARIZE1', 'DEPOLARIZE2', 'X_ERROR', 'Y_ERROR', 'Z_ERROR'];

  function addRule(scope = 'gate_rules', name = '', rule = {
    after: {},
    flip_result: 0
  }) {
    const row = document.createElement('details');
    row.className = 'noise-rule';
    row.open = true;
    row.innerHTML = '<summary>Noise rule</summary><label>Applies to<select class="rule-scope"><option value="any_clifford_1q_rule">All one-qubit Clifford gates</option><option value="any_clifford_2q_rule">All two-qubit Clifford gates</option><option value="gate_rules">Named gate / reset</option><option value="measure_rules">Measurement basis</option></select></label><label class="rule-name-label">Gate name or Pauli basis<input class="rule-name" placeholder="e.g. H, RX, Z, XX"></label><div class="rule-channels"></div><label>Measurement result flip<input class="rule-flip" type="number" min="0" max="1" step="any" value="0"></label><button class="remove-rule" type="button">Remove rule</button>';
    row.querySelector('.rule-scope').value = scope;
    row.querySelector('.rule-name').value = name;
    row.querySelector('.rule-flip').value = rule.flip_result || 0;
    for (const channel of channels) {
      const label = document.createElement('label');
      label.textContent = channel;
      const input = document.createElement('input');
      input.type = 'number';
      input.min = 0;
      input.max = 1;
      input.step = 'any';
      input.dataset.channel = channel;
      input.value = rule.after[channel] ?? 0;
      label.append(input);
      row.querySelector('.rule-channels').append(label);
    }
    const update = () => {
      const general = row.querySelector('.rule-scope').value.startsWith('any_');
      row.querySelector('.rule-name-label').hidden = general;
      row.querySelector('.rule-flip').disabled = general;
      if (general) row.querySelector('.rule-flip').value = 0;
      row.querySelector('summary').textContent = general ? (row.querySelector('.rule-scope').value === 'any_clifford_1q_rule' ? 'All one-qubit Clifford gates' : 'All two-qubit Clifford gates') : (row.querySelector('.rule-scope').value === 'gate_rules' ? 'Gate · ' : 'Measurement · ') + (row.querySelector('.rule-name').value || 'choose a name');
    };
    row.querySelector('.rule-scope').onchange = update;
    row.querySelector('.rule-name').oninput = update;
    update();
    row.querySelector('.remove-rule').onclick = () => row.remove();
    el('noise-rules').append(row);
  }

  function resetRules() {
    el('noise-rules').replaceChildren();
    const p = Number(el('noise').value) || 0;
    el('noise-idle').value = p;
    el('noise-wait').value = 0;
    addRule('any_clifford_1q_rule', '', {
      after: {
        DEPOLARIZE1: p
      }
    });
    addRule('any_clifford_2q_rule', '', {
      after: {
        DEPOLARIZE2: p
      }
    });
    for (const basis of ['X', 'Y', 'Z', 'XX', 'YY', 'ZZ']) addRule('measure_rules', basis, {
      after: {},
      flip_result: p
    });
    for (const [gate, channel] of [
        ['RX', 'Z_ERROR'],
        ['RY', 'X_ERROR'],
        ['R', 'X_ERROR']
      ]) addRule('gate_rules', gate, {
      after: {
        [channel]: p
      }
    });
    for (const row of el('noise-rules').children) row.open = false;
  }

  function update() {
    const k = Number(el('distance').value);
    el('distance-hint').textContent = `Nominal code distance: ${2*k+1}. Actual distance depends on graph and convention; larger scales require more time and memory.`;
    el('height-preview').textContent = `At k = ${k}: ${Number(el('height-slope').value)*k+Number(el('height-offset').value)} stabilizer rounds.`;
    const model = el('noise-model').value;
    el('custom-noise').hidden = model !== 'custom';
    el('noise-p-control').hidden = ['none', 'custom'].includes(model);
    el('noise-help').textContent = model === 'si1000' ? 'SI1000 requires p ≤ 0.2 and only supports Z measurements and resets. TQEC does not automatically convert incompatible circuits; compilation may fail.' : model === 'custom' ? 'Missing rules cause a compilation error; remove a general rule only when named rules cover those gates.' : 'Use zero probability or No added noise for an ideal circuit.';
    el('database-controls').hidden = el('detector-cache').value === 'disabled';
  }
  for (const id of ['distance', 'height-slope', 'height-offset', 'noise-model', 'detector-cache']) el(id).addEventListener('input', update);
  el('add-noise-rule').onclick = () => addRule();
  el('reset-noise-rules').onclick = resetRules;
  el('import-database').onclick = async () => {
    try {
      const file = el('database-file').files[0];
      if (!file) throw Error('Choose a TQEC JSON database first.');
      const response = await fetch('/api/detector-database', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Studio-Token': document.querySelector('meta[name="studio-token"]').content
        },
        body: JSON.stringify({
          name: el('database-name').value,
          database: JSON.parse(await file.text())
        })
      });
      const result = await response.json();
      if (!response.ok) throw Error(result.error);
      el('database-status').textContent = `Imported ${result.entries} entries into ${result.name}.`;
    } catch (error) {
      el('database-status').textContent = error.message;
    }
  };
  window.compilationSettings = () => {
    const inputs = [...el('panel-compile').querySelectorAll('input[type="number"]')].filter(input => !input.disabled && !input.closest('[hidden]'));
    for (const input of inputs)
      if (input.value === '' || !input.validity.valid) {
        for (let parent = input.parentElement; parent; parent = parent.parentElement)
          if (parent.tagName === 'DETAILS') parent.open = true;
        input.reportValidity();
        throw Error('Check the compilation settings: a numeric field is missing or invalid.');
      }
    const custom = {
      idle_depolarization: Number(el('noise-idle').value),
      additional_depolarization_waiting_for_m_or_r: Number(el('noise-wait').value),
      gate_rules: {},
      measure_rules: {},
      any_clifford_1q_rule: null,
      any_clifford_2q_rule: null
    };
    if (el('noise-model').value === 'custom')
      for (const row of el('noise-rules').children) {
        const scope = row.querySelector('.rule-scope').value,
          name = row.querySelector('.rule-name').value.trim().toUpperCase(),
          after = {};
        for (const input of row.querySelectorAll('[data-channel]'))
          if (Number(input.value)) after[input.dataset.channel] = Number(input.value);
        const rule = {
          after,
          flip_result: Number(row.querySelector('.rule-flip').value)
        };
        if (scope.startsWith('any_')) {
          if (custom[scope]) throw Error('Only one rule is allowed for each general Clifford group.');
          custom[scope] = rule;
        } else {
          if (!name || Object.hasOwn(custom[scope], name)) throw Error('Each named rule needs a unique gate or basis.');
          custom[scope][name] = rule;
        }
      }
    return {
      k: Number(el('distance').value),
      convention: el('convention').value,
      observable_mode: el('observable-mode').value,
      block_temporal_height: {
        slope: Number(el('height-slope').value),
        offset: Number(el('height-offset').value)
      },
      noise_model: el('noise-model').value,
      noise_p: Number(el('noise').value),
      custom_noise: el('noise-model').value === 'custom' ? custom : {},
      manhattan_radius: Number(el('detector-radius').value),
      detector_cache: el('detector-cache').value,
      database_name: el('database-name').value
    };
  };
  el('panel-compile').addEventListener('input', () => {
    if (!el('results').hidden) el('job').textContent = 'Settings changed. Downloads belong to the completed run; compile again to apply these settings.';
  });
  resetRules();
  update();
})();
