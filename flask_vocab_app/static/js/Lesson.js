import { h, useState } from './preact_deps.js';

window.LessonComponent = function LessonComponent({ lessonId }) {
    const [error, setError] = useState(null);
    const [success, setSuccess] = useState(null);

    return h('div', { class: 'lesson-content' }, [
        error && h('div', { class: 'alert alert-danger mb-3' }, error),
        success && h('div', { class: 'alert alert-success mb-3' }, success),
        !lessonId &&
            h('div', { class: 'mb-3' }, [
                h('h2', null, 'Создать новый урок'),
                h(
                    'form',
                    {
                        'hx-post': '/lessons/create',
                        'hx-target': '#lesson-content',
                        'hx-swap': 'innerHTML',
                        'hx-indicator': '#create-spinner',
                        enctype: 'multipart/form-data',
                    },
                    [
                        h('div', { class: 'mb-3' }, [
                            h(
                                'label',
                                { for: 'title', class: 'form-label' },
                                'Название урока',
                            ),
                            h('input', {
                                type: 'text',
                                class: 'form-control',
                                id: 'title',
                                name: 'title',
                                required: true,
                            }),
                        ]),
                        h('div', { class: 'mb-3' }, [
                            h(
                                'label',
                                { for: 'description', class: 'form-label' },
                                'Описание урока (фокус для ИИ)',
                            ),
                            h('textarea', {
                                class: 'form-control',
                                id: 'description',
                                name: 'description',
                                rows: 4,
                                placeholder:
                                    'Опишите, на чем сосредоточен урок, чтобы направить ИИ (например, грамматика, лексика, разговорные фразы)',
                            }),
                        ]),
                        h('div', { class: 'mb-3' }, [
                            h(
                                'label',
                                { for: 'pdf', class: 'form-label' },
                                'Загрузить учебник (PDF)',
                            ),
                            h('input', {
                                type: 'file',
                                class: 'form-control',
                                id: 'pdf',
                                name: 'pdf',
                                accept: '.pdf',
                            }),
                        ]),
                        h('div', { class: 'mb-3' }, [
                            h(
                                'label',
                                { for: 'images', class: 'form-label' },
                                'Загрузить изображения урока',
                            ),
                            h('input', {
                                type: 'file',
                                class: 'form-control',
                                id: 'images',
                                name: 'images',
                                accept: '.jpg,.jpeg,.png',
                                multiple: true,
                                onChange: (e) => {
                                    if (e.target.files.length > 5) {
                                        e.target.value = '';
                                        e.target.setCustomValidity(
                                            'Можно загрузить максимум 5 изображений.',
                                        );
                                        e.target.reportValidity();
                                    } else {
                                        e.target.setCustomValidity('');
                                    }
                                },
                            }),
                        ]),
                        h(
                            'button',
                            { type: 'submit', class: 'btn btn-primary' },
                            'Создать урок',
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
