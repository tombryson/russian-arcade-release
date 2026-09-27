(() => {
    const binding = Symbol.for('russian-arcade.activities-menu');
    if (document[binding]) return;
    document[binding] = true;

    document.addEventListener('click', event => {
        const link = event.target.closest?.('a[href]');
        document.querySelectorAll('details[data-activities-menu][open]').forEach(menu => {
            if (!menu.contains(event.target) || (link && menu.contains(link))) {
                menu.open = false;
            }
        });
    });

    document.addEventListener('keydown', event => {
        if (event.key !== 'Escape') return;
        document.querySelectorAll('details[data-activities-menu][open]').forEach(menu => {
            menu.open = false;
            menu.querySelector('summary')?.focus();
        });
    });
})();
