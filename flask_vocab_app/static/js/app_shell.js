(function () {
    if (window.russianArcadeShellLoaded) return;
    window.russianArcadeShellLoaded = true;

    const loadedScripts = new Map();
    const storyMounts = new WeakSet();
    const submittingButtons = new WeakMap();
    const generatingStories = new WeakMap();
    let posChart = null;
    let initFrame = null;
    let initializedMainContent = null;
    let initializedPage = '';
    const shellText = {
        en: {
            applying_cleaning: 'Applying cleaning...',
            apply_cleaning_error: 'Could not apply cleaning',
            cards: 'cards',
            cleaning_applied: 'Cleaning applied.',
            create_sentence_error: 'Could not create sentence',
            creating_sentence: 'Creating sentence...',
            data_load_error: 'Error loading data',
            max_images: 'You can upload a maximum of 5 images.',
            open_cleaning_error: 'Could not open cleaning',
            open_sync_error: 'Could not open sync',
            processing: ' Processing...',
            processing_complete: ' Processing complete',
            progress_error: ' Progress error',
            select_topic_difficulty: 'Choose a topic and difficulty.',
            sentence_table_error: 'Could not show the sentence table.',
            story_text_error: 'Could not show the story text.',
            story_connection_error: 'The connection was interrupted. Your current work is still here. Try again.',
            sync_complete: 'Sync complete.',
            sync_imported: 'Imported', sync_exported: 'Exported', sync_pending: 'Awaiting enrichment', sync_failed: 'Failed',
            sync_empty: 'No words to sync.',
            sync_error: 'Could not sync',
            syncing: 'Syncing...',
            timer_expired: 'Time expired!',
            timer_remaining: 'Time remaining',
            vocab_loading: 'Loading words...',
        },
        ru: {
            applying_cleaning: 'Применяем очистку...',
            apply_cleaning_error: 'Не удалось применить очистку',
            cards: 'карточек',
            cleaning_applied: 'Очистка применена.',
            create_sentence_error: 'Не удалось создать предложение',
            creating_sentence: 'Создаем предложение...',
            data_load_error: 'Ошибка загрузки данных',
            max_images: 'Можно загрузить максимум 5 изображений.',
            open_cleaning_error: 'Не удалось открыть очистку',
            open_sync_error: 'Не удалось открыть синхронизацию',
            processing: ' Обработка...',
            processing_complete: ' Обработка завершена',
            progress_error: ' Ошибка прогресса',
            select_topic_difficulty: 'Выберите тему и сложность.',
            sentence_table_error: 'Не удалось показать таблицу предложений.',
            story_text_error: 'Не удалось показать текст истории.',
            story_connection_error: 'Соединение прервалось. Ваша работа осталась на странице. Попробуйте ещё раз.',
            sync_complete: 'Синхронизация завершена.',
            sync_imported: 'Импортировано', sync_exported: 'Экспортировано', sync_pending: 'Ожидают обогащения', sync_failed: 'Ошибки',
            sync_empty: 'Нет слов для синхронизации.',
            sync_error: 'Не удалось синхронизировать',
            syncing: 'Синхронизация...',
            timer_expired: 'Время истекло!',
            timer_remaining: 'Осталось',
            vocab_loading: 'Загрузка слов...',
        },
    };

    function t(key) {
        const language = document.documentElement.lang === 'ru' ? 'ru' : 'en';
        return shellText[language]?.[key] || shellText.en[key] || key;
    }

    function loadScript(src) {
        if (loadedScripts.has(src)) return loadedScripts.get(src);
        const existing = document.querySelector(`script[src="${src}"]`);
        if (existing) {
            const promise = Promise.resolve();
            loadedScripts.set(src, promise);
            return promise;
        }
        const promise = new Promise((resolve, reject) => {
            const script = document.createElement('script');
            script.src = src;
            script.onload = resolve;
            script.onerror = reject;
            document.head.appendChild(script);
        });
        loadedScripts.set(src, promise);
        return promise;
    }

    function formatNumber(num) {
        return String(num).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    }

    function loadPreact() {
        return import('/static/js/preact_deps.js');
    }

    function showShellMessage(message, type = 'danger') {
        const main = document.getElementById('mainContent');
        if (!main) return;
        let status = document.getElementById('shell-status');
        if (!status) {
            status = document.createElement('div');
            status.id = 'shell-status';
            status.className = 'shell-status';
            status.setAttribute('aria-live', 'polite');
            main.prepend(status);
        }
        status.innerHTML = '';
        const alert = document.createElement('div');
        alert.className = `alert alert-${type}`;
        alert.setAttribute(type === 'danger' ? 'role' : 'aria-live', type === 'danger' ? 'alert' : 'polite');
        alert.textContent = message;
        status.appendChild(alert);
    }

    function setReadingGenerationState(form, isSubmitting) {
        const button = form.querySelector('button[type="submit"]');
        const label = form.querySelector('[data-reading-button-label]');
        if (!button || !label) return;
        if (isSubmitting) {
            if (generatingStories.has(form)) return;
            generatingStories.set(form, { label: label.textContent, disabled: button.disabled });
            button.disabled = true;
            label.textContent = form.dataset.preparing;
            form.setAttribute('aria-busy', 'true');
        } else {
            const original = generatingStories.get(form);
            if (original) {
                label.textContent = original.label;
                button.disabled = original.disabled;
            }
            generatingStories.delete(form);
            form.removeAttribute('aria-busy');
        }
        const spinner = form.querySelector('[data-reading-spinner]');
        if (spinner) spinner.hidden = !isSubmitting;
        const status = form.querySelector('[data-reading-generation-status]');
        if (status) status.textContent = isSubmitting ? form.dataset.preparing : '';
    }

    function setSubmittingState(element, isSubmitting) {
        const readingForm = element?.closest?.('#comprehension-form');
        if (readingForm) {
            setReadingGenerationState(readingForm, isSubmitting);
            return;
        }
        const button = element?.matches?.('button')
            ? element
            : element?.querySelector?.('button[type="submit"], button[hx-post]');
        if (!button) return;
        if (isSubmitting) {
            submittingButtons.set(button, button.disabled);
            button.disabled = true;
            button.classList.add('is-submitting');
        } else {
            button.disabled = submittingButtons.get(button) || false;
            button.classList.remove('is-submitting');
            submittingButtons.delete(button);
        }
    }

    function startProgress(sessionId, progressElementId) {
        const progressSpan = document.getElementById(progressElementId);
        if (!progressSpan || !sessionId) return;
        progressSpan.textContent = t('processing');
        const source = new EventSource(`/progress/${sessionId}`);
        source.onmessage = function (event) {
            const data = JSON.parse(event.data);
            if (data.complete) {
                progressSpan.textContent = t('processing_complete');
                source.close();
            } else {
                progressSpan.textContent = `${t('processing')} ${data.current}/${data.total}`;
            }
        };
        source.onerror = function () {
            progressSpan.textContent = t('progress_error');
            source.close();
        };
    }

    function getRequestPath(event) {
        const elt = event.detail?.elt;
        return elt?.getAttribute('hx-post') || elt?.getAttribute('hx-get') || '';
    }

    function hideModal(id) {
        const modalElement = document.getElementById(id);
        if (!modalElement || !window.bootstrap) return;
        const modal =
            window.bootstrap.Modal.getInstance(modalElement) ||
            new window.bootstrap.Modal(modalElement);
        modal.hide();
    }

    function hideClosestModal(element) {
        const modalElement = element?.closest?.('.modal');
        if (!modalElement?.id) return;
        hideModal(modalElement.id);
    }

    function initTooltips(root) {
        if (!window.bootstrap) return;
        root.querySelectorAll('[data-bs-toggle="tooltip"]').forEach((el) => {
            if (!window.bootstrap.Tooltip.getInstance(el)) {
                new window.bootstrap.Tooltip(el);
            }
        });
    }

    function updateActiveNav(path = window.location.pathname) {
        const links = document.querySelectorAll(
            '#sidebar .sidebar-link, #sidebar .sidebar-icon-link',
        );
        const matches = Array.from(links).filter(link => {
            const href = link.getAttribute('href') || '';
            return href === path || (href !== '/' && !href.includes('#') && path.startsWith(href + '/'));
        });
        const longest = Math.max(0, ...matches.map(link => link.getAttribute('href').length));
        links.forEach((link) => {
            const href = link.getAttribute('href') || '';
            const isActive = matches.includes(link) && href.length === longest;
            const current = isActive;
            link.classList.toggle('active', current);
            if (current) {
                link.setAttribute('aria-current', 'page');
                const moreTools = link.closest('.sidebar-more-tools');
                if (moreTools) moreTools.open = true;
            } else {
                link.removeAttribute('aria-current');
            }
        });
    }

    function sidebarNavLink(element) {
        return element?.closest?.(
            '#sidebar a.sidebar-link[href], #sidebar a.sidebar-icon-link[href]',
        );
    }

    function isBoostedSidebarNavigation(element) {
        const link = sidebarNavLink(element);
        return Boolean(link && link.getAttribute('hx-boost') !== 'false');
    }

    function closeMobileSidebarAfterNavigation(event) {
        const { target, requestConfig, elt, xhr } = event.detail || {};
        const source = requestConfig?.elt || elt;
        if (target?.id !== 'mainContent' || !isBoostedSidebarNavigation(source) ||
            window.innerWidth >= 992 || (xhr && (xhr.status < 200 || xhr.status >= 400))) return;
        const menu = document.getElementById('sidebarNav');
        if (!menu?.classList.contains('show')) return;
        if (window.bootstrap?.Collapse) {
            window.bootstrap.Collapse.getOrCreateInstance(menu, { toggle: false }).hide();
        } else {
            menu.classList.remove('show');
            document.querySelector('[data-bs-target="#sidebarNav"]')?.setAttribute('aria-expanded', 'false');
        }
    }

    function setMainLoading(isLoading) {
        const main = document.getElementById('mainContent');
        if (main) main.classList.toggle('is-loading', isLoading);
    }

    function toggleLeftSidebar() {
        document.getElementById('sidebar')?.classList.toggle('hidden');
        document
            .getElementById('mainContent')
            ?.classList.toggle('left-sidebar-hidden');
    }

    function getMainContent(root = document) {
        if (root?.id === 'mainContent') return root;
        return document.getElementById('mainContent');
    }

    function getCurrentPage(root = document) {
        const main = getMainContent(root);
        if (main?.dataset.page) return main.dataset.page;
        const path = window.location.pathname;
        if (path.startsWith('/tools/anki')) return 'flashcards';
        if (path.startsWith('/vocab')) return 'vocab';
        if (path.startsWith('/comprehension')) return 'comprehension';
        if (path.startsWith('/writing')) return 'writing';
        if (path.startsWith('/lessons')) return 'lessons';
        if (path.startsWith('/word_jumble')) return 'word_jumble';
        if (path.startsWith('/sentences/saved')) return 'sentences_saved';
        if (path.startsWith('/sentences')) return 'sentences';
        return '';
    }

    function scheduleInitPage(root = document, force = false) {
        if (initFrame) cancelAnimationFrame(initFrame);
        initFrame = requestAnimationFrame(() => {
            initFrame = null;
            const main = getMainContent(root);
            if (!main) return;
            const page = getCurrentPage(main);
            if (!force && main === initializedMainContent && page === initializedPage) {
                return;
            }
            initializedMainContent = main;
            initializedPage = page;
            initPage(main);
        });
    }

    window.toggleDifficulty = function (checkbox) {
        document
            .querySelectorAll('.difficulty-checkbox')
            .forEach((cb) => (cb.disabled = checkbox.checked));
        if (!checkbox.checked) {
            document
                .querySelectorAll('.difficulty-checkbox')
                .forEach((cb) => (cb.checked = false));
        }
    };

    window.togglePos = function (checkbox) {
        document
            .querySelectorAll('.pos-checkbox')
            .forEach((cb) => (cb.disabled = checkbox.checked));
        if (!checkbox.checked) {
            document
                .querySelectorAll('.pos-checkbox')
                .forEach((cb) => (cb.checked = false));
        }
    };

    window.updateDashboard = async function () {
        const metricsDiv = document.getElementById('metrics');
        if (!metricsDiv) return;

        const topicCheckbox = document.getElementById('topicFilter');
        const topicSelect = document.getElementById('topicSelect');
        if (topicSelect && topicCheckbox) {
            topicSelect.disabled = !topicCheckbox.checked;
        }

        const params = new URLSearchParams();
        if (topicCheckbox?.checked) params.append('topic', 'any');

        try {
            const chartReady = loadScript(
                'https://cdn.jsdelivr.net/npm/apexcharts@3.53.0/dist/apexcharts.min.js',
            ).catch(() => null);
            const response = await fetch(`/metrics?${params.toString()}`, {
                headers: { Accept: 'application/json; charset=utf-8' },
            });
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const data = await response.json();
            if (!document.body.contains(metricsDiv)) return;

            const totalWords = document.getElementById('total');
            const flashcardTotal = document.getElementById('flashcards-total');
            const flashcardPercentage = document.getElementById(
                'flashcard-percentage',
            );
            const difficultyTable = document.getElementById('difficultyTable');
            const posChartDiv = document.getElementById('scoreDistribution');

            if (totalWords) totalWords.textContent = formatNumber(data.total_words || 0);
            if (flashcardTotal)
                flashcardTotal.textContent = formatNumber(data.flashcard_total || 0);
            if (flashcardPercentage)
                flashcardPercentage.textContent = (
                    data.flashcard_percentage || 0
                ).toFixed(2);

            if (difficultyTable) {
                difficultyTable.innerHTML = '';
                Object.entries(data.difficulty_distribution || {}).forEach(
                    ([diff, count]) => {
                        const wordCount =
                            (data.difficulty_word_counts || {})[diff] || 1;
                        const percentage =
                            wordCount > 0
                                ? ((count / wordCount) * 100).toFixed(2)
                                : '0.00';
                        difficultyTable.insertAdjacentHTML(
                            'beforeend',
                            `<tr><td>${diff}</td><td>${formatNumber(
                                count,
                            )}</td><td class="text-primary fw-bold">${percentage}%</td></tr>`,
                        );
                    },
                );
            }

            if (topicSelect) {
                topicSelect.innerHTML = '';
                Object.entries(data.topic_distribution || {}).forEach(
                    ([topic, count]) => {
                        if (count <= 0) return;
                        const option = document.createElement('option');
                        option.value = topic;
                        option.textContent = `${topic} (${formatNumber(
                            count,
                        )} ${t('cards')}`;
                        topicSelect.appendChild(option);
                    },
                );
            }

            await chartReady;
            if (!window.ApexCharts || !posChartDiv) return;
            const chartType =
                document.querySelector('input[name="chartType"]:checked')?.value ||
                'pos';
            const source =
                chartType === 'case'
                    ? data.case_distribution || {}
                    : data.pos_distribution || {};
            const labels = Object.keys(source).filter((_, i) => {
                return Object.values(source)[i] > 0;
            });
            const series = Object.values(source).filter((value) => value > 0);
            if (posChart) posChart.destroy();
            posChart = new window.ApexCharts(posChartDiv, {
                chart: { type: 'pie', animations: { enabled: false } },
                series,
                labels,
                legend: { position: 'bottom' },
            });
            posChart.render();
        } catch (error) {
            if (!document.body.contains(metricsDiv)) return;
            const totalWords = document.getElementById('total');
            const flashcardTotal = document.getElementById('flashcards-total');
            const flashcardPercentage = document.getElementById(
                'flashcard-percentage',
            );
            const difficultyTable = document.getElementById('difficultyTable');
            if (totalWords) totalWords.textContent = t('data_load_error');
            if (flashcardTotal) flashcardTotal.textContent = t('data_load_error');
            if (flashcardPercentage) flashcardPercentage.textContent = '0.00';
            if (difficultyTable) {
                difficultyTable.innerHTML =
                    `<tr><td colspan="3">${t('data_load_error')}</td></tr>`;
            }
        }
    };

    let vocabMount;
    let vocabMountRequest = 0;
    async function loadVocabTable() {
        return Promise.all([loadPreact(), import('/static/js/VocabTable.js?v=2')]);
    }

    function refreshVocabSource() {
        const source = document.getElementById('source-cloud')?.checked
            ? 'cloud'
            : 'db';
        window.handleSourceChange(source);
    }

    window.handleSourceChange = async function (source) {
        const requestId = ++vocabMountRequest;
        if (vocabMount) { vocabMount.render(null, vocabMount.node); vocabMount = null; }
        const dynamicContent = document.getElementById('dynamic-vocab-content');
        if (!dynamicContent) return;
        if (source === 'db') {
            dynamicContent.innerHTML =
                `<div id="vocab-table"><div class="loading-message" role="status">${t('vocab_loading')}</div></div>`;
            const [{ h, render }, { VocabTable }] = await loadVocabTable();
            if (requestId !== vocabMountRequest || !document.body.contains(dynamicContent)) return;
            vocabMount = {render, node:document.getElementById('vocab-table')};
            vocabMount.node.replaceChildren();
            render(
                h(VocabTable, { source: 'db' }),
                vocabMount.node,
            );
        } else if (window.htmx) {
            window.htmx.ajax('GET', '/vocab?page=1&source=cloud', {
                target: '#dynamic-vocab-content',
                swap: 'outerHTML',
            });
        }
    };

    window.openEditModal = function (word) {
        const modal = document.getElementById('editWordModal');
        if (!modal || !window.bootstrap) return;
        modal.querySelector('#edit-old-word').value = word;
        modal.querySelector('#edit-new-word').value = word;
        new window.bootstrap.Modal(modal).show();
    };

    async function mountStoryText() {
        const storyContainer = document.getElementById('story-container');
        if (!storyContainer || !storyContainer.dataset.words) return;
        try {
            const [{ h, render }, { StoryText }] = await Promise.all([
                loadPreact(),
                import('/static/js/StoryText.js?v=3'),
            ]);
            const words = JSON.parse(storyContainer.dataset.words || '[]');
            const taskId = document.querySelector('#question-form [name="task_id"]')?.value || storyContainer.dataset.taskId;
            // Replace the readable server fallback once per DOM node. A restored
            // HTMX page has a new node and must be mounted again.
            if (!storyMounts.has(storyContainer)) {
                storyContainer.replaceChildren();
                storyMounts.add(storyContainer);
            }
            render(
                h(StoryText, {
                    words,
                    source: { story_id: storyContainer.dataset.storyId || '', story_key: storyContainer.dataset.storyKey || '', ...(taskId ? {task_id: taskId} : {}) },
                    initialVisibility:
                        storyContainer.dataset.visibility || 'revealed',
                }),
                storyContainer,
            );
        } catch (error) {
            storyContainer.innerHTML =
                `<div class="alert alert-danger">${t('story_text_error')}</div>`;
        }
    }

    document.addEventListener('arcade:comprehension-transcript', mountStoryText);

    async function confirmSync() {
        const dataElement = document.getElementById('sync-to-add');
        const feedback = document.getElementById('sync-preview-feedback');
        const button = document.querySelector('[data-action="confirm-sync"]');
        if (button?.disabled) return;
        let toAdd = [];
        try {
            toAdd = JSON.parse(dataElement?.textContent || '[]');
        } catch {
            toAdd = [];
        }
        if (!Array.isArray(toAdd)) {
            if (feedback)
                feedback.innerHTML =
                    `<div class="alert alert-info">${t('sync_empty')}</div>`;
            return;
        }
        if (feedback)
            feedback.innerHTML =
                `<div class="loading-message" role="status">${t('syncing')}</div>`;
        if (button) button.disabled = true;
        try {
            const response = await fetch('/sync', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ to_add: toAdd }),
            });
            const data = await response.json();
            if (!response.ok || data.error) throw new Error(data.error || `HTTP ${response.status}`);
            hideModal('syncPreviewModal');
            const summary = `${t('sync_complete')} ${t('sync_imported')}: ${data.imported?.length || 0}; ${t('sync_exported')}: ${data.exported?.length || 0}; ${t('sync_pending')}: ${data.enrichment_pending?.length || 0}; ${t('sync_failed')}: ${data.failed?.length || 0}.`;
            showShellMessage([summary, ...(data.warnings || [])].join(' '), data.status === 'partial' ? 'warning' : 'success');
            refreshVocabSource();
        } catch (error) {
            if (feedback) {
                const alert = document.createElement('div');
                alert.className = 'alert alert-danger';
                alert.textContent = `${t('sync_error')}: ${error.message}`;
                feedback.replaceChildren(alert);
            }
        } finally {
            if (button) button.disabled = false;
        }
    }

    async function handleSanitizationSubmit(event) {
        event.preventDefault();
        const form = event.target;
        const feedback = document.getElementById('sanitize-preview-feedback');
        if (feedback)
            feedback.innerHTML =
                `<div class="loading-message" role="status">${t('applying_cleaning')}</div>`;
        try {
            const response = await fetch(form.action, {
                method: 'POST',
                body: new FormData(form),
            });
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const data = await response.json();
            if (data.status !== 'success') {
                throw new Error(data.error || 'Unknown error');
            }
            hideModal('sanitizePreviewModal');
            showShellMessage(t('cleaning_applied'), 'success');
            if (window.htmx) {
                window.htmx.ajax('GET', '/vocab?page=1&source=cloud', {
                    target: '#dynamic-vocab-content',
                    swap: 'outerHTML',
                });
            }
        } catch (error) {
            if (feedback)
                feedback.innerHTML = `<div class="alert alert-danger">${t('apply_cleaning_error')}: ${error.message}</div>`;
        }
    }

    function initPage(root) {
        updateActiveNav();
        initTooltips(root);
        const page = getCurrentPage(root);
        if (page !== 'vocab' && vocabMount) { ++vocabMountRequest; vocabMount.render(null, vocabMount.node); vocabMount = null; }
        if (page === 'flashcards') window.updateDashboard();
        if (page === 'vocab') {
            const source = document.getElementById('source-db')?.checked
                ? 'db'
                : 'cloud';
            if (source === 'db') window.handleSourceChange(source);
        }
        if (page === 'comprehension') mountStoryText();
    }

    document.addEventListener(
        'click',
        (event) => {
            if (event.target.closest('#sidebarToggle')) {
                event.preventDefault();
                event.stopImmediatePropagation();
                toggleLeftSidebar();
            }
        },
        true,
    );

    document.addEventListener('click', (event) => {
        const navLink = sidebarNavLink(event.target);
        if (navLink && navLink.getAttribute('hx-boost') !== 'false') {
            updateActiveNav(new URL(navLink.href, window.location.origin).pathname);
        }
        const editButton = event.target.closest('[data-edit-word]');
        if (editButton) {
            window.openEditModal(editButton.dataset.editWord || '');
        }
        if (event.target.closest('[data-action="confirm-sync"]')) {
            confirmSync();
        }
        const closeButton = event.target.closest('[data-close-modal]');
        if (closeButton) {
            if (closeButton.dataset.closeModal) {
                hideModal(closeButton.dataset.closeModal);
            } else {
                hideClosestModal(closeButton);
            }
        }
    });

    document.addEventListener('change', (event) => {
        const target = event.target;
        if (target.id === 'diffAny') window.toggleDifficulty(target);
        if (target.id === 'posAny') window.togglePos(target);
        if (target.id === 'source-db' || target.id === 'source-cloud') {
            window.location.assign(`/vocab?source=${target.value}`);
        }
        if (target.name === 'chartType' || target.id === 'topicFilter') {
            window.updateDashboard();
        }
        if (target.id === 'images' && target.files.length > 5) {
            target.value = '';
            showShellMessage(t('max_images'), 'warning');
        }
    });

    document.addEventListener('submit', (event) => {
        if (event.target.id === 'sanitization-form') {
            handleSanitizationSubmit(event);
        }
        // A normal form submission still acknowledges the wait if HTMX is unavailable.
        if (event.target.id === 'comprehension-form' && !window.htmx) {
            if (generatingStories.has(event.target)) event.preventDefault();
            else if (!event.defaultPrevented) setReadingGenerationState(event.target, true);
        }
    });

    const mainObserver = new MutationObserver(() => {
        const main = document.getElementById('mainContent');
        if (main && main !== initializedMainContent) scheduleInitPage(main);
    });
    mainObserver.observe(document.body, { childList: true, subtree: true });

    document.addEventListener('DOMContentLoaded', () => scheduleInitPage(document, true));
    document.addEventListener('input', (event) => {
        if (!event.target.closest('#question-form')) return;
        const workspace = document.querySelector('.reading-workspace');
        if (workspace) {
            workspace.dataset.dirty = 'true';
            workspace.dataset.revision = String(Number(workspace.dataset.revision || 0) + 1);
        }
    });
    window.addEventListener('beforeunload', (event) => {
        if (document.querySelector('.reading-workspace')?.dataset.dirty !== 'true') return;
        event.preventDefault();
        event.returnValue = '';
    });
    document.body.addEventListener('htmx:beforeRequest', (event) => {
        const workspace = document.querySelector('.reading-workspace');
        const target = event.detail.target;
        if (workspace?.dataset.dirty === 'true' &&
            ['mainContent', 'comprehension-content'].includes(target?.id) &&
            !window.confirm(workspace.dataset.leaveMessage)) {
            event.preventDefault();
            return;
        }
        if (['/comprehension/save', '/comprehension/answer'].includes(getRequestPath(event)) && workspace) {
            event.detail.elt.dataset.saveRevision = workspace.dataset.revision || '0';
        }
        if (event.detail.elt?.closest('.reading-workspace')) {
            document.getElementById('reading-action-feedback')?.replaceChildren();
        }
        if (isBoostedSidebarNavigation(event.detail.elt)) setMainLoading(true);
        if (!event.detail.elt?.closest?.('#comprehension-form')) setSubmittingState(event.detail.elt, true);
    });
    document.body.addEventListener('htmx:beforeSend', (event) => {
        // Start only after request cancellation/validation and form serialization.
        const form = event.detail.elt?.closest?.('#comprehension-form');
        if (form) setReadingGenerationState(form, true);
        if (['/comprehension/answer', '/comprehension/save', '/comprehension/generate_more_questions'].includes(getRequestPath(event))) {
            event.detail.xhr.arcadeReadingTask = document.querySelector('#question-form input[name="task_id"]')?.value;
            event.detail.xhr.arcadeReadingForm = document.getElementById('question-form');
        }
    });
    document.body.addEventListener('htmx:beforeSwap', (event) => {
        const issuedTask = event.detail.xhr?.arcadeReadingTask;
        if (issuedTask && (issuedTask !== document.querySelector('#question-form input[name="task_id"]')?.value
            || event.detail.xhr.arcadeReadingForm !== document.getElementById('question-form'))) {
            // A slow response from an earlier question set must not replace the
            // current task's feedback or its out-of-band submission identity.
            event.detail.shouldSwap = false;
            return;
        }
        const feedback = document.getElementById('reading-action-feedback');
        if (feedback && event.detail.xhr?.status >= 400 &&
            event.detail.target?.closest('.reading-workspace')) {
            // A provider failure must not replace the story, questions or draft.
            event.detail.target = feedback;
            event.detail.shouldSwap = true;
        }
    });
    document.body.addEventListener('htmx:afterRequest', (event) => {
        const path = getRequestPath(event);
        const xhrText = event.detail?.xhr?.response || 'Unknown error';
        setSubmittingState(event.detail.elt, false);

        const issuedTask = event.detail.xhr?.arcadeReadingTask;
        const sameReadingTask = !issuedTask || (issuedTask === document.querySelector('#question-form input[name="task_id"]')?.value
            && event.detail.xhr.arcadeReadingForm === document.getElementById('question-form'));
        if (['/comprehension/save', '/comprehension/answer'].includes(path) && event.detail.successful && sameReadingTask) {
            const workspace = document.querySelector('.reading-workspace');
            if (workspace && (workspace.dataset.revision || '0') === event.detail.elt.dataset.saveRevision) {
                workspace.dataset.dirty = 'false';
            }
        }

        if (path === '/generate') {
            const resultDiv = document.getElementById('result');
            if (resultDiv?.dataset.sessionId) {
                startProgress(resultDiv.dataset.sessionId, 'progress');
            }
        }
        if (path === '/generate_word_forms') {
            const wordResultDiv = document.getElementById('word-result');
            if (wordResultDiv?.dataset.sessionId) {
                startProgress(wordResultDiv.dataset.sessionId, 'word-progress');
            }
        }
        if (path === '/sync_vocab' && !event.detail.successful) {
            hideModal('syncPreviewModal');
            showShellMessage(`${t('open_sync_error')}: ${xhrText}`);
        }
        if (path === '/sanitize_vocab' && !event.detail.successful) {
            hideModal('sanitizePreviewModal');
            showShellMessage(`${t('open_cleaning_error')}: ${xhrText}`);
        }
        if (path === '/sync' && event.detail.successful) {
            hideModal('syncPreviewModal');
            refreshVocabSource();
        }
        if (path === '/apply_sanitization' && event.detail.successful) {
            hideModal('sanitizePreviewModal');
            if (window.htmx) {
                window.htmx.ajax('GET', '/vocab?page=1&source=cloud', {
                    target: '#dynamic-vocab-content',
                    swap: 'outerHTML',
                });
            }
        }
        if (path === '/add_word' && !event.detail.successful) {
            const resultDiv = document.getElementById('add-word-result');
            if (resultDiv) resultDiv.innerHTML = xhrText;
        }
        if (path === '/add_word' && event.detail.successful) {
            const input = document.getElementById('add-word-input');
            if (input) input.value = '';
            hideModal('addWordModal');
            refreshVocabSource();
        }
        if (path === '/edit_word' && !event.detail.successful) {
            const resultDiv = document.getElementById('edit-word-result');
            if (resultDiv) resultDiv.innerHTML = xhrText;
        }
        if (path === '/edit_word' && event.detail.successful) {
            hideModal('editWordModal');
            refreshVocabSource();
        }
    });
    document.body.addEventListener('htmx:afterSwap', (event) => {
        if (event.detail.target.id === 'questions-section') mountStoryText();
        if (event.detail.target.id === 'mainContent') {
            setMainLoading(false);
            return;
        }
        if (event.detail.target.id === 'comprehension-content') {
            mountStoryText();
            if (event.detail.target.querySelector('[data-story-loaded]')) {
                for (const id of ['saved-stories', 'new-story']) {
                    document.getElementById(id)?.removeAttribute('open');
                }
                const workspace = document.querySelector('.reading-workspace');
                if (workspace) workspace.dataset.dirty = document.querySelector('#question-form input[name="task_id"]') ? 'false' : 'true';
                document.getElementById('reading-story-title')?.focus();
            }
        }
        if (event.detail.target.id === 'questions-section') {
            const workspace = document.querySelector('.reading-workspace');
            if (workspace) workspace.dataset.dirty = 'true';
        }
    });
    document.body.addEventListener('htmx:afterSettle', (event) => {
        setMainLoading(false);
        if (event.detail.target.id === 'mainContent') {
            closeMobileSidebarAfterNavigation(event);
            scheduleInitPage(event.detail.target, true);
            return;
        }
        updateActiveNav();
    });
    document.body.addEventListener('htmx:historyRestore', () => {
        scheduleInitPage(document, true);
    });
    document.body.addEventListener('htmx:beforeHistorySave', () => {
        const form = document.getElementById('comprehension-form');
        if (form) setReadingGenerationState(form, false);
        // HTMX caches HTML, which otherwise contains the initial textarea value.
        document.querySelectorAll('#question-form textarea').forEach((answer) => {
            answer.defaultValue = answer.value;
        });
    });
    document.body.addEventListener('htmx:responseError', () => setMainLoading(false));
    document.body.addEventListener('htmx:sendError', () => setMainLoading(false));
    for (const eventName of ['htmx:sendError', 'htmx:timeout', 'htmx:sendAbort']) {
        document.body.addEventListener(eventName, (event) => {
            const form = event.detail?.elt?.closest?.('#comprehension-form');
            if (!form) return;
            setReadingGenerationState(form, false);
            const feedback = document.getElementById('reading-action-feedback');
            if (feedback) feedback.textContent = t('story_connection_error');
        });
    }
    window.addEventListener('pageshow', () => {
        const form = document.getElementById('comprehension-form');
        if (form) setReadingGenerationState(form, false);
    });
})();
