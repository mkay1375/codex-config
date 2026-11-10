---
name: readable-html
description: Turn long text, a manuscript, or an extracted document into a self-contained offline HTML reader with book-sized pages, a table of contents, reading-position memory, and mobile controls. Use for requests to make text into a paginated HTML book or کتاب‌خوان تک‌فایلی, rather than a report or general website.
---

# Readable HTML

Deliver one portable `.html` file based on [assets/reader-template.html](assets/reader-template.html). Keep the approved reading interface; replace its content rather than redesigning it. Fonts, styles, scripts, icons, and document data belong inside the file. Reading must work offline; only the user-triggered ChatGPT action opens an external site.

## Prepare the text

- Use the supplied text or extract it with an available format-appropriate tool. For an existing reader HTML, extract its source data, not navigation labels or duplicated rendered pages. Do not invent missing passages or silently drop footnotes, tables, code, or appendices. Represent these as plain-text blocks when the reader cannot preserve their original layout; explain material limitations.
- Preserve wording, punctuation, and order. This task authorizes pagination, not rewriting or summarization. Only repair extraction artifacts or normalize spacing when requested. Read large inputs programmatically in full rather than reconstructing them from truncated tool output.
- Identify the language and direction explicitly. Use Persian Vazir for Persian; the template includes both font weights and the license. English uses a serif reading face; other languages can use suitable installed/system fallback fonts. If a particular script requires an embedded font, use an appropriately licensed font and include its license. Preserve mixed-script names, numbers, and quotes.
- Build a table of contents from genuine chapter or section headings, retaining the source hierarchy in titles where necessary. Do not turn arbitrary first sentences into chapter names. For unstructured text, use `text` or `paragraphs` without `chapters`; chapter navigation is then hidden while search and bookmarks remain available.

Read [references/content-schema.md](references/content-schema.md) when preparing structured JSON or setting explicit page breaks.

## Choose page boundaries

A page is a stable reading unit, not a viewport height. Font size changes must not silently change its identity or count. Mobile pages may need scrolling.

Default pagination groups intact paragraphs, aiming for roughly 200–300 words. It balances a short final page where possible. Prefer complete topics, arguments, quotations, and their explanations over an exact word limit. Shorter or longer pages are acceptable when required by meaning. Keep short complete works intact.

For a long paragraph or an especially meaningful boundary, review the surrounding text and use sentence-complete blocks plus the optional chapter `pageStarts` indices. Never cut through a sentence, dialogue turn, list item, or parenthetical explanation just to hit a word count. Preserve the original text and separators when subdividing a paragraph; compare reconstruction with the source. For scripts without word spaces, use sensible paragraph/topic boundaries and explicit page starts rather than trusting the default word-count heuristic.

Use «صفحه» / “Page” for reader navigation, counts, search results, and bookmarks. Headings may still use the source's own terminology. Do not label reader pages «بخش».

## Build

Use the dependency-free helper rather than interpolating source text into JavaScript:

```bash
python3 <skill-dir>/scripts/build_reader.py input.json --output reader.html
# Plain UTF-8 text without a known outline:
python3 <skill-dir>/scripts/build_reader.py input.txt --title 'عنوان کتاب' --lang fa --output reader.html
```

Resolve `<skill-dir>` to this skill's actual directory. The helper embeds JSON safely, validates chapter/page boundaries, and namespaces local storage for each document. It never edits the input or relies on the original workspace paths.

Preserve these template behaviors:

- Right-to-left or left-to-right reading; Vazir embedded for Persian.
- Warm yellow paper in light mode and muted yellow/olive in dark mode. Default to the system appearance, respond to live system changes, and allow manual light/dark/system selection.
- Full-width mobile text; desktop contents rail; reachable bottom previous/next, copy, ChatGPT, bookmark, contents, and settings controls. Icon buttons retain accessible names.
- Current page out of the **whole document**, including chapter transitions. Previous/next must cross chapter boundaries correctly.
- Save location, scroll offset, typography, theme, and bookmarks locally. Opening settings or contents adds a history entry, so browser/Android Back first closes the panel. Closing it manually must consume that entry as well.
- ChatGPT receives selected text inside the reading area, otherwise the current page, with title/chapter context. Open a prepared prompt; do not send messages automatically or add an API key. For long prompts, copy the text and open ChatGPT with a clear paste instruction. Report clipboard/popup failure truthfully. Shift-click copies the prompt only.

## Verify and deliver

Run the helper on representative input and open the generated artifact in a browser when available. Check the invariants that matter to the supplied document:

- Every source passage appears exactly once, in order, and every TOC item lands on its proper first page. Inspect around chapter transitions and manually curated boundaries.
- At mobile width (~390 px, also check 320 px) and desktop width, no horizontal overflow or unreachable controls. Check one RTL and one LTR input if language behavior changed.
- Previous/next, total page count, search, bookmarks, reload/resume, light/dark/system mode, and panel Back/close behavior work. Reading and embedded fonts work with the network off. ChatGPT can be tested by capturing the intended URL without contacting the service.
- A source string containing `</script>` remains literal text and cannot execute code. There are no runtime errors or unintended network dependencies.

Return a link to the final HTML and screenshots when possible. Mention meaningful extraction or pagination limitations. Keep intermediate JSON, scripts, and screenshots out of the deliverable folder unless requested. Do not require publishing, a server, installation, or account sign-in to read the result.
