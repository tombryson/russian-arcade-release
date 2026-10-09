/**
 * Bind the shared mobile header disclosure without intercepting navigation.
 * @param {HTMLElement} root
 * @returns {() => void}
 */
export function bindHeaderMenu(root) {
    const toggle = root.querySelector('.header-menu-toggle');
    const panel = root.querySelector('[data-header-menu-panel]');
    if (!toggle || !panel) return () => {};

    const document = root.ownerDocument;
    const window = document.defaultView;
    const mobile = window.matchMedia?.('(max-width: 700px)');
    const isOpen = () => root.dataset.expanded === 'true';
    const close = () => {
        panel.querySelectorAll('details[open]').forEach(menu => { menu.open = false; });
        root.dataset.expanded = 'false';
        toggle.setAttribute('aria-expanded', 'false');
    };
    const toggleMenu = () => {
        if (isOpen() || mobile?.matches === false) {
            close();
            return;
        }
        root.dataset.expanded = 'true';
        toggle.setAttribute('aria-expanded', 'true');
    };
    const click = event => {
        if (!isOpen()) return;
        if (!root.contains(event.target)) {
            close();
            return;
        }
        const link = event.target.closest?.('a[href]');
        if (!link || !panel.contains(link) || event.defaultPrevented || event.button ||
            event.metaKey || event.ctrlKey || event.shiftKey || event.altKey ||
            link.target || link.hasAttribute('download')) return;
        close();
    };
    const escape = event => {
        if (event.key !== 'Escape' || !isOpen()) return;
        // Close nested disclosures before their own Escape handlers can focus
        // a summary that is about to become hidden with the mobile panel.
        close();
        event.preventDefault();
        event.stopPropagation();
        toggle.focus({ preventScroll: true });
    };
    const resize = () => { if (!mobile.matches) close(); };

    close();
    toggle.addEventListener('click', toggleMenu);
    document.addEventListener('click', click);
    document.addEventListener('keydown', escape, true);
    window.addEventListener('hashchange', close);
    mobile?.addEventListener('change', resize);
    return () => {
        toggle.removeEventListener('click', toggleMenu);
        document.removeEventListener('click', click);
        document.removeEventListener('keydown', escape, true);
        window.removeEventListener('hashchange', close);
        mobile?.removeEventListener('change', resize);
    };
}
