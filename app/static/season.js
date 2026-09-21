document.addEventListener('DOMContentLoaded', () => {
  const seasonPicker = document.getElementById('season');
  seasonPicker?.addEventListener('change', () => seasonPicker.form.submit());

  const chart = document.getElementById('winLossChart');
  if (chart && window.Chart) {
    new Chart(chart, {
      type: 'pie',
      data: {
        labels: ['Wins', 'Losses', 'Draws'],
        datasets: [{
          label: 'Match outcomes',
          data: JSON.parse(chart.dataset.outcomes),
          backgroundColor: ['rgba(40, 167, 69, .7)', 'rgba(220, 53, 69, .7)', 'rgba(255, 193, 7, .7)'],
          borderColor: ['rgb(40, 167, 69)', 'rgb(220, 53, 69)', 'rgb(255, 193, 7)'],
          borderWidth: 1,
        }],
      },
      options: { responsive: true, plugins: { legend: { position: 'top' } } },
    });
  }

  if (document.getElementById('player-leaderboard') && window.List) {
    new List('player-leaderboard', { valueNames: ['player', 'starts', 'bench', 'total'] });
  }
});
