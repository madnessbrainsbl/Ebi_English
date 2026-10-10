# Сторонние компоненты и материалы

MIT-лицензия проекта распространяется на собственный код и собственные упражнения. Сторонние данные и библиотеки сохраняют отдельные условия. База `content.db` объединяет материалы разных источников и не является целиком MIT-датасетом.

## Библиотеки

| Компонент | Версия | Лицензия / уведомление |
|---|---|---|
| [PDF.js, Mozilla](https://github.com/mozilla/pdf.js) | 6.4.299 | Apache-2.0, `licenses/pdfjs-dist-LICENSE.txt` |
| [Mammoth, Michael Williamson](https://github.com/mwilliamson/mammoth.js) | 1.13.0 | BSD-2-Clause, `licenses/mammoth-LICENSE.txt` |
| [sql.js](https://github.com/sql-js/sql.js) | 1.14.2 | MIT, `licenses/sql-js-LICENSE.txt`; SQLite скомпилирован в WASM |
| [Marked, Christopher Jeffrey и участники](https://github.com/markedjs/marked) | 18.1.0 | MIT, `licenses/marked-LICENSE.txt` |
| [DOMPurify, Cure53 и участники](https://github.com/cure53/DOMPurify) | 3.4.16 | Apache-2.0 OR MPL-2.0; выбрана Apache-2.0, `DOMPurify-LICENSE.txt` |
| [Playwright, Microsoft](https://github.com/microsoft/playwright) | 1.63.0 | Apache-2.0, инструмент разработки; устанавливается через npm |

Библиотеки получены из официального npm registry. Версии, адреса архивов, npm integrity и SHA-256 включённых файлов зафиксированы в `vendor-manifest.json`. PDF.js загружается из локального Blob-модуля; отдельные файлы и встроенные копии имеют одинаковое содержимое. Документы пользователей не входят в репозиторий.

## Словари и учебные материалы

- **FreeDict/WikDict English–Russian.** `freedict.js` — преобразованный словарь: объединены переводы, удалены ударения и служебная разметка. Автор сборки — Karl Bartel; исходные данные — участники Wiktionary через DBnary. [Исходник FreeDict](https://download.freedict.org/generated/eng-rus/eng-rus.tei), [WikDict](https://www.wikdict.com/page/about), [DBnary](https://kaiko.getalp.org/about-dbnary/). Условия конкретного TEI: [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/); текст в `licenses/CC-BY-SA-3.0.txt`. Данные этого словаря и их адаптации сохраняют CC BY-SA 3.0.
- **CEFR-J Vocabulary Profile 1.5.** Compiled by Yukio Tono, Tokyo University of Foreign Studies; copyright Tono Laboratory, TUFS. [CEFR-J](http://www.cefr-j.org/download.html), [Open Language Profiles](https://github.com/openlanguageprofiles/olp-en-cefrj). Используется выборка слов с уровнями и добавленными переводами/примерами. Условия и полная цитата — `licenses/CEFR-J-TERMS.md`; исследования и коммерческое использование разрешены при атрибуции.
- **CMU Pronouncing Dictionary.** Copyright Carnegie Mellon University, участники CMUdict. Из исходного словаря сформирована таблица `pronunciations` с IPA. [Исходник](https://github.com/cmusphinx/cmudict), уведомление BSD в `licenses/CMUdict-LICENSE.txt`.
- **MITRE ATT&CK.** Copyright The MITRE Corporation. Выбраны названия техник и определения, добавлены переводы и учебная разбивка. [Исходник](https://github.com/mitre-attack/attack-stix-data), [условия](https://attack.mitre.org/resources/legal-and-branding/terms-of-use/), полный текст в `licenses/MITRE-ATTACK-LICENSE.txt`. ATT&CK — товарный знак MITRE; проект не заявляет одобрения MITRE.
- **OpenStax University Physics Volume 3.** Samuel J. Ling, Jeff Sanny, William Moebs; OpenStax, Rice University. [Книга](https://openstax.org/details/books/university-physics-volume-3). Выбраны термины/определения и добавлены переводы. [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), `licenses/CC-BY-4.0.txt`.
- **OpenStax Biology 2e.** Mary Ann Clark, Matthew Douglas, Jung Choi; OpenStax, Rice University. [Книга](https://openstax.org/details/books/biology-2e). Выбраны термины/определения и добавлены переводы. CC BY 4.0, `licenses/CC-BY-4.0.txt`.
- **WithEnglishWeCan — generated English phrasal verbs.** [Источник](https://github.com/WithEnglishWeCan/generated-english-phrasal-verbs). Выборка фразовых глаголов с учебными переводами и примерами. Указанная upstream-лицензия — MIT, подтверждение в `licenses/Phrasal-Verbs-README.md`; прежняя запись о Public Domain Dedication исправлена. Применяется текст MIT из `LICENSE` с сохранением этой атрибуции.
- **Неправильные глаголы.** Формы глаголов являются языковыми фактами; упражнения и примеры заданы непосредственно в `import_phrasal_and_irregular.py`. MIT проекта не приписывается стороннему приложению art-mironoff/irregular-verbs, для которого лицензия не подтверждена.
- **Averil Coxhead — Academic Word List.** [Справочный список слов](https://www.wgtn.ac.nz/lals/resources/academicwordlist). Используются выбранные слова; переводы, определения и примеры проекта не представляют копию полного списка AWL.
- **Cambridge English / CEFR.** [Описание уровня Proficiency](https://www.cambridgeenglish.org/exams-and-tests/proficiency/) используется как справка по уровням, без воспроизведения экзаменационных материалов. Cambridge Exams Publishing Open Cloze (CEPOC) в поставку не входит: упражнения `CL_A2`, `CL_B1`, `CL_B2` заменены собственными; исходные упражнения поставки — `dev/context_grammar.json`.

Базовые колоды и собственные примеры проходят структурные проверки; это не означает ручную редактуру каждого перевода. Справочные ссылки на образовательные сайты не изменяют лицензии сторонних произведений.

## Предложения и аудио Tatoeba

[Tatoeba](https://tatoeba.org/) и её участники — источник части предложений, переводов и ссылок на произношение. Полные атрибуции по совпадению с официальным экспортом: `licenses/tatoeba-sentences.tsv` (ID, язык, автор, текст, лицензия, исходная страница). Для адаптированных переводов исходные участники сохраняют авторство своих предложений. Удалённые или снятые с авторства записи экспорта могут иметь автора `\N`; исходная страница по ID остаётся ссылкой на историю записи.

Текстовые предложения используют [CC BY 2.0 France](https://creativecommons.org/licenses/by/2.0/fr/). См. [условия Tatoeba](https://tatoeba.org/en/terms_of_use), разделы 6.2 и 6.5. При распространении базы сохраняйте атрибуции и лицензионные ссылки.

Аудиофайлы не поставляются: браузер загружает их с Tatoeba. `licenses/tatoeba-audio.tsv` содержит ID предложения, ID аудио, автора, лицензию и дополнительный URL атрибуции. Ссылки без указанной лицензии исключены. Лицензии отдельных авторов различаются:

- CC BY 4.0 — требуется атрибуция.
- CC BY-SA 4.0 — атрибуция и сохранение лицензии адаптаций.
- CC BY-NC 4.0 — дополнительно некоммерческое использование.
- CC BY-NC-ND 3.0 — некоммерческое использование, без распространения адаптаций.

Тексты перечисленных лицензий приложены в `licenses/`. Аудио CK также требует сохранения ссылки [ManyThings.org](http://www.manythings.org/tatoeba). Коммерческое использование кода не предоставляет права коммерческого использования аудио с NC-условием.

Архивные JS-корпуса, скриншоты и материалы OpenSubtitles в репозиторий не включены. Некоторые короткие общеупотребительные фразы могут встречаться у нескольких источников; это не означает лицензирование чужого корпуса лицензией проекта.
