/* Suggest the topic's course level without overwriting an explicit choice. */
(() => {
  const key = Symbol.for('russian-arcade.curriculum');
  if (document[key]) return;
  document[key] = true;
  document.addEventListener('change', event => {
    const target = event.target;
    if (!(target instanceof Element)) return;
    const form = target.closest('form[data-curriculum-setup]');
    if (!form) return;
    if (target.matches('[data-curriculum-level]')) {
      form.dataset.levelExplicit = 'true';
      return;
    }
    if (!target.matches('[data-curriculum-topic]') || form.dataset.levelExplicit === 'true') return;
    const suggestion = target.selectedOptions[0]?.dataset.level;
    const level = form.querySelector('[data-curriculum-level]');
    if (!suggestion || !level) return;
    const option = [...level.options].find(item => (item.dataset.level || item.value) === suggestion);
    if (option) level.value = option.value;
  });
})();
