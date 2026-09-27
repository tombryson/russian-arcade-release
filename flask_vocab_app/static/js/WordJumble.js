import { h, useState } from './preact_deps.js';

window.WordJumbleComponent = function WordJumbleComponent({ gameId }) {
    const [error, setError] = useState(null);
    const [success, setSuccess] = useState(null);

    return h('div', { class: 'jumble-content' }, [
        error && h('div', { class: 'alert alert-danger mb-3' }, error),
        success && h('div', { class: 'alert alert-success mb-3' }, success),
        !gameId &&
            h('div', { class: 'mb-3' }, [
                h('h2', null, 'Создать новую игру'),
                h(
                    'form',
                    {
                        'hx-post': '/word_jumble/create',
                        'hx-target': '#jumble-content',
                        'hx-swap': 'innerHTML',
                        'hx-indicator': '#create-spinner',
                    },
                    [
                        h('div', { class: 'mb-3' }, [
                            h(
                                'label',
                                { for: 'topic', class: 'form-label' },
                                'Тема',
                            ),
                            h(
                                'select',
                                {
                                    class: 'form-select',
                                    id: 'topic',
                                    name: 'topic',
                                },
                                [
                                    h('option', { value: 'any' }, 'Любая'),
                                    // Topics will be populated server-side
                                ],
                            ),
                        ]),
                        h('div', { class: 'mb-3' }, [
                            h(
                                'label',
                                { for: 'difficulty', class: 'form-label' },
                                'Уровень сложности',
                            ),
                            h(
                                'select',
                                {
                                    class: 'form-select',
                                    id: 'difficulty',
                                    name: 'difficulty',
                                },
                                [
                                    h(
                                        'option',
                                        { value: 'beginner' },
                                        'Начальный',
                                    ),
                                    h(
                                        'option',
                                        { value: 'intermediate' },
                                        'Средний',
                                    ),
                                    h(
                                        'option',
                                        { value: 'advanced' },
                                        'Продвинутый',
                                    ),
                                ],
                            ),
                        ]),
                        h(
                            'button',
                            { type: 'submit', class: 'btn btn-primary' },
                            'Создать игру',
                        ),
                        h(
                            'div',
                            {
                                id: 'create-spinner',
                                class: 'htmx-indicator mt-3',
                            },
                            [
                                h(
                                    'div',
                                    {
                                        class: 'spinner-border text-primary',
                                        role: 'status',
                                    },
                                    [
                                        h(
                                            'span',
                                            { class: 'visually-hidden' },
                                            'Создание...',
                                        ),
                                    ],
                                ),
                                h('span', null, ' Создание...'),
                            ],
                        ),
                    ],
                ),
            ]),
    ]);
};
