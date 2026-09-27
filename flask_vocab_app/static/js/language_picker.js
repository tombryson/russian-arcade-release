(() => {
    document.addEventListener('click', (event) => {
        document.querySelectorAll('.language-picker[open]').forEach((picker) => {
            if (!picker.contains(event.target)) picker.open = false;
        });
    });
    document.addEventListener('keydown', (event) => {
        if (event.key !== 'Escape') return;
        document.querySelectorAll('.language-picker[open]').forEach((picker) => {
            const hadFocus = picker.contains(document.activeElement);
            picker.open = false;
            if (hadFocus) picker.querySelector('summary').focus();
        });
    });
    document.addEventListener('submit', (event) => {
        if (!event.target.matches('.language-picker-options')) return;
        // Navigation may have changed the current activity without a page reload.
        event.target.elements.next.value = location.pathname + location.search + location.hash;
    });
})();
