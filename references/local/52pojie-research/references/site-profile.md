# 52pojie Public Site Profile

This profile records the public interfaces used by `52pojie-research`. It is based on direct retrieval of the site on 2026-09-15.

## Public routes

| Purpose | URL pattern | Notes |
| --- | --- | --- |
| Forum listing | `https://www.52pojie.cn/forum-{fid}-{page}.html` | Discuz! X3 style listing; page 1 exposes pagination and thread links. |
| Forum RSS | `https://www.52pojie.cn/forum.php?mod=rss&fid={fid}` | XML feed with the latest 20 threads, title, URL, description, author, and publication date. |
| Hot guide | `https://www.52pojie.cn/forum.php?mod=guide&view=hot` | Public cross-forum hot-thread listing; useful for discovery, not a substitute for thread reading. |
| Thread page | `https://www.52pojie.cn/thread-{tid}-{page}-1.html` | Public HTML contains the subject and post bodies when the page is available. |

The supplied URL, `forum-4-1.html`, resolves to the 逆向资源区 (`fid=4`). The observed page exposed 106 listing pages and categories such as Android Tools, Debuggers, Disassemblers, PEtools, Packers, Cryptography, Unpackers, `.NET`, Scripts, and plugins.

## Encoding and selectors

- The HTML and RSS responses declare `gbk`; decode bytes before parsing.
- Forum thread titles use links with class `xst` and a `thread-{tid}-1-1.html` URL.
- Thread subjects use `id="thread_subject"`.
- Post bodies use ids beginning with `postmessage_`.
- Thread pagination exposes a page count in the public page navigation; selected pages can be read sequentially.
- Author and publication metadata use `res-author` and ids beginning with `authorposton`.
- Images and downloads are exposed as attachment metadata. The parser records their presence but does not fetch them.

## Access limits

The site's `robots.txt` disallows `/search.php`, member and home pages, API paths, posting and redirect paths, and attachment query paths. This route therefore performs keyword filtering over public listings and RSS rather than calling the internal search form. A missing keyword match is not evidence that the forum has no matching post.

## Open-source survey

- [leslie-lss/52pojie](https://github.com/leslie-lss/52pojie): the closest historical crawler; it parses forum ids, thread details, and replies across pages, but requires MongoDB/Redis and contains old hard-coded infrastructure. It is a parsing reference, not a dependency.
- [comddy/52pojie](https://github.com/comddy/52pojie): reads the public hot guide and writes the first 50 titles to a local text file; it does not read thread bodies.
- [jueinin/python](https://github.com/jueinin/python/blob/master/52%E7%A0%B4%E8%A7%A3%E5%86%99%E5%85%A5xls.py): reads a fixed forum list and exports rows to XLS; it has no thread-detail path.
- [XIU2/UserScript](https://github.com/XIU2/UserScript/blob/master/52pojie-Enhanced.user.js): maintained browser enhancement with public forum, guide, search, and thread auto-pagination; it changes the browser DOM rather than returning structured research data.
- [bd-dxg/52pjhelper](https://github.com/bd-dxg/52pjhelper): browser management helper for profile, violation, and duplicate-reply views; it is not a public research reader.
- [Hans774882968/52pojie-catalog-enhancer](https://github.com/Hans774882968/52pojie-catalog-enhancer): adds a catalog to headings in the current thread page; it has no retrieval interface.
- [alexleung0808-beep/52pojie-skill](https://github.com/alexleung0808-beep/52pojie-skill): organizes user-provided 52pojie material into security research skills; it explicitly does not access the forum or download files.
- [Syz87/52pojie-post-review](https://github.com/Syz87/52pojie-post-review): reviews pasted content against forum rules; it does not retrieve posts.
- [ganlvtech/down_52pojie_cn](https://github.com/ganlvtech/down_52pojie_cn) and [anhkgg/Get52PojieTools](https://github.com/anhkgg/Get52PojieTools): target `down.52pojie.cn` file listings or downloads, not forum posts.
- [lonnnnnng/52pojie_Sign](https://github.com/lonnnnnng/52pojie_Sign), [Mrzqd/52pojie_sign](https://github.com/Mrzqd/52pojie_sign), [guapier/52pojie](https://github.com/guapier/52pojie), and [hfxjd9527/52pojie_login](https://github.com/hfxjd9527/52pojie_login): sign-in, login, or captcha automation; outside this route's public-read scope.

Conclusion: no maintained, dependency-light, callable public forum reader was found. The bundled child skill keeps the useful public URL patterns and multi-page parsing behavior while returning JSON and avoiding login, browser automation, databases, proxies, and attachment access.

These projects were reviewed as possible reusable components and are kept as provenance only. The bundled parser is limited to public read operations.
