document.addEventListener('DOMContentLoaded', async () => {
  const form = document.querySelector('.teamsheet-form');
  if (!form) return;
  const inputs = [...form.querySelectorAll('.player-input')];
  const warning = document.getElementById('duplicate-warning');
  const knownPlayers = new Map();

  const update = () => {
    const seen = new Map();
    const duplicates = new Set();
    inputs.forEach((input) => {
      const key = input.value.trim().toLocaleLowerCase();
      input.classList.remove('input-error');
      if (!key) return;
      if (seen.has(key)) {
        duplicates.add(input.value.trim());
        input.classList.add('input-error');
        seen.get(key).classList.add('input-error');
      } else {
        seen.set(key, input);
      }

      const badge = document.getElementById(`milestone-${input.dataset.position}`);
      badge.hidden = true;
      const count = knownPlayers.get(input.value.trim());
      if (count !== undefined && ((count + 1) % 50 === 0 || count === 0)) {
        badge.textContent = count === 0 ? 'Debut' : `${count + 1}th cap`;
        badge.hidden = false;
      }
    });
    warning.hidden = duplicates.size === 0;
    warning.textContent = duplicates.size ? `Duplicate players selected: ${[...duplicates].join(', ')}` : '';
  };

  inputs.forEach((input) => input.addEventListener('input', update));
  try {
    const response = await fetch(form.dataset.playerUrl, { headers: { Accept: 'application/json' } });
    if (!response.ok) return;
    const players = await response.json();
    const datalist = document.getElementById('playerNames');
    players.forEach(({ name, count }) => {
      knownPlayers.set(name, count);
      const option = document.createElement('option');
      option.value = name;
      datalist.appendChild(option);
    });
  } finally {
    update();
  }
});
