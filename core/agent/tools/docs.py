# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""Documentation search for agents.

Serves the same markdown source the in-app /docs pages are built from —
synced into ``docs/user/`` by ``scripts/sync_user_docs.sh`` (the UI compiles
them into its JS bundle, so the API needs its own copy). Results are raw
markdown, never rendered HTML: that is what an agent can actually quote and
reason over.

Pages are split into sections at ``##`` headings; search scores title,
heading and body matches separately so "how do I release feedback" lands on
the right section of the grading guide rather than the whole page.
"""
from __future__ import annotations

import re
from pathlib import Path

from django.conf import settings

from core.agent import errors, shaping
from core.agent.registry import SCOPE_READ, tool

_DOCS_DIR = Path(settings.BASE_DIR) / 'docs' / 'user'

# Same substitution DocsLoader.ts applies in the UI: docs hardcode the
# production API URL; rewrite it to this deployment's.
_HARDCODED_API_URL = 'https://codepost-api.cs.rutgers.edu'

# module-level cache, invalidated when any file's mtime changes
_cache: dict = {'stamp': None, 'pages': []}


def _frontmatter(raw: str) -> tuple[dict, str]:
    match = re.match(r'^---\r?\n(.*?)\r?\n---\r?\n(.*)$', raw, re.S)
    if not match:
        return {}, raw
    meta = {}
    for line in match.group(1).splitlines():
        if ':' in line:
            key, _, value = line.partition(':')
            meta[key.strip()] = value.strip()
    return meta, match.group(2)


def _split_sections(body: str) -> list[dict]:
    """Split at ## headings; the preamble before the first ## is its own section."""
    sections = []
    current = {'heading': '', 'lines': []}
    for line in body.splitlines():
        if line.startswith('## '):
            if current['lines']:
                sections.append(current)
            current = {'heading': line[3:].strip(), 'lines': []}
        else:
            current['lines'].append(line)
    if current['lines']:
        sections.append(current)
    return [{'heading': s['heading'], 'text': '\n'.join(s['lines']).strip()}
            for s in sections if '\n'.join(s['lines']).strip() or s['heading']]


def _load_pages() -> list[dict]:
    files = sorted(_DOCS_DIR.glob('*.md')) if _DOCS_DIR.is_dir() else []
    stamp = tuple((f.name, f.stat().st_mtime_ns) for f in files)
    if _cache['stamp'] == stamp:
        return _cache['pages']

    api_url = getattr(settings, 'API_URL', '').rstrip('/')
    pages = []
    for f in files:
        raw = f.read_text(encoding='utf-8', errors='replace')
        if api_url:
            raw = raw.replace(_HARDCODED_API_URL, api_url)
        meta, body = _frontmatter(raw)
        pages.append({
            'key': meta.get('key') or f.stem,
            'title': meta.get('title') or f.stem,
            'category': meta.get('category', ''),
            'body': body.strip(),
            'sections': _split_sections(body),
        })
    _cache['stamp'], _cache['pages'] = stamp, pages
    return pages


def _score(terms: list[str], page: dict, section: dict) -> float:
    """Cheap weighted term scoring — title 5, heading 3, body 1, phrase +4."""
    title = page['title'].lower()
    heading = section['heading'].lower()
    text = section['text'].lower()
    score = 0.0
    for term in terms:
        score += 5 * title.count(term)
        score += 3 * heading.count(term)
        score += min(text.count(term), 5)          # cap body spam
    phrase = ' '.join(terms)
    if len(terms) > 1 and (phrase in text or phrase in heading):
        score += 4
    return score


@tool(
    name='codepost_search_docs',
    title='Search codePost docs',
    description=(
        'Search the codePost user documentation (instructor guides, grading '
        'and publishing workflow, quizzes, autograder testing, SDK, FAQ). '
        'Returns matching sections as raw MARKDOWN you can quote directly.\n\n'
        'Pass query to search; pass page (a key from the results or from '
        'calling with no arguments, which lists all pages) to fetch one whole '
        'page. Use this to answer "how do I…" questions about codePost itself '
        'before guessing.'
    ),
    input_schema={
        'type': 'object',
        'properties': {
            'query': {'type': 'string',
                      'description': 'Keywords to search for.'},
            'page': {'type': 'string',
                     'description': "A page key, e.g. 'instructor-grading'."},
            'limit': {'type': 'integer', 'default': 5, 'maximum': 10,
                      'description': 'Max sections returned for a search.'},
        },
        'additionalProperties': False,
    },
    min_scope=SCOPE_READ,
    read_only=True,
    # Docs are deployment-level, not course data: no courseId needed even on
    # personal-token connections, and no course capability applies.
    course_bound=False,
)
def search_docs(ctx, query: str = '', page: str = '', limit: int = 5):
    pages = _load_pages()
    if not pages:
        raise errors.ToolError(
            'PRECONDITION_NOT_MET',
            'No documentation is bundled with this deployment.',
            remedy='Run scripts/sync_user_docs.sh in the codePost-api repo and '
                   'redeploy; report this to the user.')

    if page:
        match = next((p for p in pages if p['key'] == page), None)
        if match is None:
            raise errors.ToolError(
                'NOT_FOUND', f"No docs page with key '{page}'.",
                remedy='Call codepost_search_docs with no arguments to list '
                       'the available pages.', retryable=True,
                context={'availableKeys': [p['key'] for p in pages]})
        return shaping.enforce_budget(shaping.envelope(
            {'page': {'key': match['key'], 'title': match['title'],
                      'category': match['category']},
             'markdown': match['body']},
            meta={'format': 'markdown'}))

    if not query:
        listing = [{'key': p['key'], 'title': p['title'],
                    'category': p['category']} for p in pages]
        return shaping.envelope(
            {'pages': listing},
            meta={'total': len(listing),
                  'hint': 'Search with query, or fetch one with page=<key>.'})

    terms = [t for t in re.split(r'\W+', query.lower()) if len(t) > 2]
    if not terms:
        raise errors.ToolError(
            'PRECONDITION_NOT_MET', 'The query has no searchable terms.',
            remedy='Use a few descriptive words, e.g. "release feedback".',
            retryable=True)

    hits = []
    for p in pages:
        for section in p['sections']:
            score = _score(terms, p, section)
            if score > 0:
                hits.append((score, p, section))
    hits.sort(key=lambda h: -h[0])

    results = []
    for score, p, section in hits[:shaping.clamp_limit(limit)]:
        heading = f"## {section['heading']}\n\n" if section['heading'] else ''
        results.append({
            'page': p['key'],
            'title': p['title'],
            'section': section['heading'] or '(introduction)',
            'markdown': heading + section['text'],
        })

    return shaping.enforce_budget(shaping.envelope(
        {'query': query, 'results': results},
        meta={'matched': len(hits), 'returned': len(results),
              'format': 'markdown',
              **({'hint': 'Fetch a full page with page=<key>.'}
                 if results else
                 {'hint': 'No matches. Call with no arguments to list pages.'})}))
