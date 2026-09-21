document.addEventListener('DOMContentLoaded', async () => {
  const form = document.querySelector('.teamsheet-form');
  if (!form) return;
  const inputs = [...form.querySelectorAll('.player-input')];
  const status = document.getElementById('form-status');
  const review = document.getElementById('review-items');
  const knownPlayers = new Map();
  let recentLineups = [];

  const keyFor = (value) => value.trim().toLocaleLowerCase();
  const closeOptions = (input) => {
    const list = document.getElementById(input.getAttribute('aria-controls'));
    list.hidden = true;
    input.setAttribute('aria-expanded', 'false');
  };

  const selectPlayer = (input, name) => {
    const duplicate = inputs.find((candidate) => candidate !== input && keyFor(candidate.value) === keyFor(name));
    if (duplicate) {
      duplicate.focus();
      status.textContent = `${name} is already selected at position ${duplicate.dataset.position}.`;
      return;
    }
    input.value = name;
    closeOptions(input);
    updateReview();
  };

  const showOptions = (input) => {
    const list = document.getElementById(input.getAttribute('aria-controls'));
    const query = keyFor(input.value);
    const selected = new Set(inputs.filter((item) => item !== input).map((item) => keyFor(item.value)).filter(Boolean));
    const matches = [...knownPlayers.keys()].filter((name) => !selected.has(keyFor(name)) && keyFor(name).includes(query)).slice(0, 8);
    list.replaceChildren();
    matches.forEach((name, index) => {
      const option = document.createElement('button');
      option.type = 'button';
      option.className = 'player-option';
      option.setAttribute('role', 'option');
      option.dataset.index = index;
      option.textContent = `${name} · ${knownPlayers.get(name)} apps`;
      option.addEventListener('mousedown', (event) => event.preventDefault());
      option.addEventListener('click', () => selectPlayer(input, name));
      list.appendChild(option);
    });
    list.hidden = matches.length === 0;
    input.setAttribute('aria-expanded', String(matches.length > 0));
  };

  const updateReview = () => {
    const seen = new Map();
    const duplicates = new Set();
    const milestones = [];
    inputs.forEach((input) => {
      const key = keyFor(input.value);
      input.classList.remove('input-error');
      if (key) {
        if (seen.has(key)) {
          duplicates.add(input.value.trim());
          input.classList.add('input-error');
          seen.get(key).classList.add('input-error');
        } else seen.set(key, input);
      }
      const badge = document.getElementById(`milestone-${input.dataset.position}`);
      badge.hidden = true;
      const count = knownPlayers.get(input.value.trim());
      if (count !== undefined && ((count + 1) % 50 === 0 || count === 0)) {
        const label = count === 0 ? `${input.value.trim()} debut` : `${input.value.trim()} reaches ${count + 1}`;
        badge.textContent = count === 0 ? 'Debut' : `${count + 1}th`;
        badge.hidden = false;
        milestones.push(label);
      }
    });
    const missingStarters = inputs.slice(0, 15).filter((input) => !input.value.trim()).length;
    const scoreA = document.getElementById('guildford_points').value;
    const scoreB = document.getElementById('opposition_points').value;
    const incompleteScore = Boolean(scoreA) !== Boolean(scoreB);
    const items = [];
    if (missingStarters) items.push(`${missingStarters} starting position${missingStarters === 1 ? '' : 's'} still blank.`);
    if (incompleteScore) items.push('Both scores are required when either score is entered.');
    if (duplicates.size) items.push(`Duplicate players: ${[...duplicates].join(', ')}.`);
    milestones.forEach((item) => items.push(`Milestone: ${item}.`));
    if (!items.length) items.push('No lineup warnings. Server validation will run when you save.');
    review.replaceChildren(...items.map((message) => { const li = document.createElement('li'); li.textContent = message; return li; }));
    const errors = missingStarters + duplicates.size + (incompleteScore ? 1 : 0);
    status.textContent = errors ? `${errors} review item${errors === 1 ? '' : 's'}` : 'Ready to save';
    status.classList.toggle('has-warning', errors > 0);
  };

  inputs.forEach((input, index) => {
    input.addEventListener('input', () => { showOptions(input); updateReview(); });
    input.addEventListener('focus', () => showOptions(input));
    input.addEventListener('blur', () => window.setTimeout(() => closeOptions(input), 100));
    input.addEventListener('keydown', (event) => {
      const list = document.getElementById(input.getAttribute('aria-controls'));
      const options = [...list.querySelectorAll('.player-option')];
      const active = document.activeElement;
      if (event.key === 'ArrowDown' && options.length) { event.preventDefault(); options[0].focus(); }
      if (event.key === 'Escape') closeOptions(input);
      if (event.key === 'ArrowUp' && active === input && index > 0) inputs[index - 1].focus();
    });
    input.closest('.player-slot').querySelector('.clear-slot').addEventListener('click', () => { input.value = ''; input.focus(); updateReview(); });
    input.closest('.player-slot').querySelector('.move-up').addEventListener('click', () => {
      if (index === 0) return;
      [inputs[index - 1].value, input.value] = [input.value, inputs[index - 1].value];
      inputs[index - 1].focus(); updateReview();
    });
    input.closest('.player-slot').querySelector('.move-down').addEventListener('click', () => {
      if (index === inputs.length - 1) return;
      [inputs[index + 1].value, input.value] = [input.value, inputs[index + 1].value];
      inputs[index + 1].focus(); updateReview();
    });
  });

  document.getElementById('copy-lineup').addEventListener('click', () => {
    const id = Number(document.getElementById('recent-lineup').value);
    const lineup = recentLineups.find((item) => item.id === id);
    if (!lineup) return;
    lineup.players.forEach((name, index) => { if (inputs[index]) inputs[index].value = name; });
    updateReview();
    status.textContent = 'Lineup copied. Match details were not changed.';
  });
  ['guildford_points', 'opposition_points'].forEach((id) => document.getElementById(id).addEventListener('input', updateReview));

  try {
    const [playersResponse, lineupsResponse] = await Promise.all([
      fetch(form.dataset.playerUrl, { headers: { Accept: 'application/json' } }),
      fetch(form.dataset.lineupsUrl, { headers: { Accept: 'application/json' } }),
    ]);
    if (playersResponse.ok) (await playersResponse.json()).forEach(({ name, count }) => knownPlayers.set(name, count));
    if (lineupsResponse.ok) {
      recentLineups = await lineupsResponse.json();
      const select = document.getElementById('recent-lineup');
      recentLineups.forEach(({ id, label }) => { const option = document.createElement('option'); option.value = id; option.textContent = label; select.appendChild(option); });
    }
  } finally { updateReview(); }
});
