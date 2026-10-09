import { bindHeaderMenu } from './header_menu.js?v=2';

const binding = Symbol.for('russian-arcade.header-menu');
if (!document[binding]) {
    const menus = new Map();
    const initialize = () => {
        for (const [root, cleanup] of menus) {
            if (!root.isConnected) {
                cleanup();
                menus.delete(root);
            }
        }
        document.querySelectorAll('[data-header-menu]').forEach(root => {
            if (!menus.has(root)) menus.set(root, bindHeaderMenu(root));
        });
    };
    document[binding] = initialize;
    document.addEventListener('htmx:afterSwap', initialize);
    document.addEventListener('htmx:historyRestore', initialize);
    initialize();
}
