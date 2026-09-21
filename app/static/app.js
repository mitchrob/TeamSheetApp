document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('[data-href]').forEach((element) => {
    element.tabIndex = 0;
    element.setAttribute('role', 'link');
    const open = () => { window.location.href = element.dataset.href; };
    element.addEventListener('click', (event) => {
      if (!event.target.closest('a, button, form, input, select, textarea')) open();
    });
    element.addEventListener('keydown', (event) => {
      if ((event.key === 'Enter' || event.key === ' ') && event.target === element) {
        event.preventDefault();
        open();
      }
    });
  });
});
