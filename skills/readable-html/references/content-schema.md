# Reader input

`build_reader.py` accepts UTF-8 `.txt` or `.json`. Extract other formats before building. JSON is one document object or a nonempty array of document objects (the latter appears as a document selector). The skill should normally deliver one book, not the template's demonstration texts.

```json
{
  "id": "optional-stable-document-id",
  "title": "عنوان کتاب",
  "subtitle": "نویسنده یا توضیح اختیاری",
  "lang": "fa",
  "dir": "rtl",
  "chapters": [
    {
      "title": "عنوان واقعی فصل",
      "paragraphs": ["پاراگراف اول…", "پاراگراف دوم…", "پاراگراف سوم…"],
      "pageStarts": [0, 2]
    }
  ]
}
```

- `title` is required for JSON. `subtitle`, `id`, `lang`, and `dir` are optional. Supply `lang` and `dir` when known; the fallback detects Persian, Arabic, Hebrew, or English heuristically. Direction is `rtl` or `ltr`; language is a BCP 47 tag such as `fa`, `en`, or `ar`.
- Choose one body form: `chapters`, `paragraphs` (array of nonempty strings), or `text` (nonempty string). `text` splits at blank lines and retains other line breaks. Use `chapters` only for meaningful source structure; otherwise chapter TOC is hidden.
- Each chapter starts a new page and requires a title and paragraph array. Navigation remains continuous across the document. Nested source headings can be expressed as readable path titles, e.g. `Chapter 2 / Sources`, without dropping heading information.
- Omit `pageStarts` for automatic paragraph grouping. To control complete-topic pagination, give **all** starts as strictly ascending zero-based paragraph indices, beginning at `0`. `[0, 2]` means paragraphs 0–1 on the first page and 2 onward on the next. `[0]` keeps the whole chapter on one page. The runtime never repaginates these groups on font changes.
- Strings are literal prose, not Markdown/HTML markup. Inline markup is not rendered. Preserve a table/code/list as a readable text block rather than silently omitting it. The template preserves line breaks inside blocks.
- Do not encode titles or paragraphs as HTML entities before writing JSON. Use a JSON serializer; the builder escapes `<`, `>`, `&`, and JavaScript line separators for safe embedding.
- An omitted document ID is derived from the content. For subsequent revisions that should retain reading positions, provide a stable ID and preserve paragraph/chapter order where possible. Positions store chapter and paragraph indices; reordering content requires a deliberate migration rather than a promise that every old bookmark still maps correctly.

The template's UI language is Persian for `fa` (including regional tags), English otherwise; content can be in other languages, with its own reading direction. Requesting another interface language requires supplying that translation separately.

The helper checks shape and page indices, not whether a heading is genuine or a page is semantically complete. Review those decisions against the source.
