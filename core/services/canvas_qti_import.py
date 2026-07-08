# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
"""
Canvas QTI / Common Cartridge import parser.

Canvas exports quizzes and question banks as an IMS Common Cartridge (.imscc/.zip)
containing IMS QTI 1.2 assessment XML. This module parses such an export into a
provider-agnostic structure that ``core.tasks.import_quiz_qti`` turns into
``Question`` / ``QuestionChoice`` / ``Quiz`` rows.

Security: parsing uses ``defusedxml`` (XXE-safe) — never the stdlib XML parser.
"""
from __future__ import annotations

import html as html_module
import io
import re
import zipfile
from typing import Optional

from defusedxml.ElementTree import fromstring


# Unambiguous HTML signals used only when ``texttype`` doesn't already say "text/html".
# Requires a closing tag, ``<br>`` or ``<img>`` so plaintext like ``a < b and c > d`` is
# never misread as HTML (which would otherwise strip the "< b ... >" as a tag).
_HTML_TAG_RE = re.compile(
    r'(?i)</\s*(div|span|p|li|ul|ol|table|tr|td|th|strong|em|code|pre|h[1-6]|blockquote|a)\s*>'
    r'|<\s*br\s*/?\s*>|<\s*img\b',
)
_BR_RE = re.compile(r'(?i)<\s*br\s*/?\s*>')
_BLOCK_CLOSE_RE = re.compile(r'(?i)</\s*(p|div|li|tr|h[1-6]|blockquote|pre)\s*>')
_TAG_RE = re.compile(r'<[^>]+>')


def _html_to_text(raw: str) -> str:
    """Convert a Canvas QTI HTML fragment to readable plain text: block/break tags
    become newlines, all other tags are stripped, and HTML entities are decoded."""
    text = _BR_RE.sub('\n', raw)
    text = _BLOCK_CLOSE_RE.sub('\n', text)
    text = _TAG_RE.sub('', text)
    text = html_module.unescape(text)
    lines = [ln.rstrip() for ln in text.splitlines()]
    text = '\n'.join(lines)
    return re.sub(r'\n{3,}', '\n\n', text).strip()


# Canvas QTI ``question_type`` → our Question.questionType. Anything not listed is
# recorded in the import summary and skipped (never silently dropped).
QTI_TYPE_MAP = {
    'multiple_choice_question': 'multiple_choice',
    'true_false_question': 'true_false',
    'multiple_answers_question': 'multiple_answers',
    'short_answer_question': 'short_answer',
    'fill_in_multiple_blanks_question': 'short_answer',
    'essay_question': 'essay',
    'text_only_question': None,  # explicitly skip non-questions
    'numerical_question': 'numerical',
}

# Auto-graded types that require a parseable correct answer (essay/code are manually graded).
_KEYED_TYPES = {'multiple_choice', 'multiple_answers', 'true_false', 'short_answer', 'numerical'}


def _lname(tag: str) -> str:
    """Local name of a possibly namespaced XML tag."""
    return tag.rsplit('}', 1)[-1]


def _iter(el, name: str):
    """Yield all descendants (and self) whose local name matches ``name``."""
    for node in el.iter():
        if _lname(node.tag) == name:
            yield node


def _first(el, name: str):
    for node in _iter(el, name):
        return node
    return None


def _material_text(el) -> str:
    """Concatenate the text of all ``mattext`` elements under ``el``.

    Canvas stores question stems as ``texttype="text/html"`` — that HTML is converted
    to clean text. Plain-text content is only entity-decoded so code like ``a < b`` is
    never mangled by tag stripping."""
    parts = []
    for mt in _iter(el, 'mattext'):
        if not mt.text:
            continue
        ttype = (mt.get('texttype') or '').lower()
        if 'html' in ttype or _HTML_TAG_RE.search(mt.text):
            txt = _html_to_text(mt.text)
        else:
            txt = html_module.unescape(mt.text).strip()
        if txt:
            parts.append(txt)
    return "\n".join(parts).strip()


def _meta_field(item, label: str) -> Optional[str]:
    """Read a Canvas ``qtimetadatafield`` value by its ``fieldlabel``."""
    for field in _iter(item, 'qtimetadatafield'):
        flabel = _first(field, 'fieldlabel')
        if flabel is not None and (flabel.text or '').strip() == label:
            fentry = _first(field, 'fieldentry')
            return (fentry.text or '').strip() if fentry is not None else None
    return None


def _question_stem(item) -> str:
    """The question text — the first ``material`` directly inside ``presentation``."""
    presentation = _first(item, 'presentation')
    if presentation is None:
        return ''
    for child in list(presentation):
        if _lname(child.tag) == 'material':
            return _material_text(child)
    # Fallback: any material under presentation that isn't inside a response label.
    return _material_text(presentation)


def _awards_credit(respcondition) -> bool:
    """Whether a ``respcondition`` sets a positive SCORE (i.e. marks the correct answer)."""
    for sv in _iter(respcondition, 'setvar'):
        varname = (sv.get('varname') or '').upper()
        action = (sv.get('action') or '').lower()
        val = (sv.text or '').strip()
        if 'SCORE' in varname or action == 'set':
            try:
                if float(val) > 0:
                    return True
            except (TypeError, ValueError):
                continue
    return False


def _parse_choices(item, qtype: str):
    """Return ``(choices, ok)`` where choices is a list of {text, isCorrect, feedback}.

    For choice/true-false/multiple-answers questions, choices come from response
    labels and correctness from the scoring conditions. For short-answer/numerical,
    the accepted answers are literal ``varequal`` values stored as correct choices.
    Essay questions have no choices.
    """
    if qtype == 'essay':
        return [], True

    # Collect selectable choices from ``render_choice`` only. Fill-in-blank questions
    # use ``render_fib`` placeholder labels, which are NOT selectable options — their
    # accepted answers come from the scoring conditions below.
    labels: list[tuple[str, str]] = []
    label_idents = set()
    for render in _iter(item, 'render_choice'):
        for rl in _iter(render, 'response_label'):
            rid = rl.get('ident') or ''
            labels.append((rid, _material_text(rl)))
            label_idents.add(rid)

    correct_idents: set[str] = set()
    literal_answers: list[str] = []
    for rc in _iter(item, 'respcondition'):
        if not _awards_credit(rc):
            continue
        # A <varequal> nested under <not> asserts the answer is WRONG (Canvas multiple_answers
        # lists excluded options this way). Exclude those, or wrong options get marked correct.
        negated = {id(ve) for neg in _iter(rc, 'not') for ve in _iter(neg, 'varequal')}
        for ve in _iter(rc, 'varequal'):
            if id(ve) in negated:
                continue
            val = (ve.text or '').strip()
            if val in label_idents:
                correct_idents.add(val)
            elif val:
                literal_answers.append(val)

    if labels:
        choices = [
            {'text': text, 'isCorrect': rid in correct_idents, 'feedback': ''}
            for rid, text in labels
        ]
        return choices, True

    # No labels: short-answer / numerical — accepted answers are the literal values.
    seen = set()
    choices = []
    for ans in literal_answers:
        if ans not in seen:
            seen.add(ans)
            choices.append({'text': ans, 'isCorrect': True, 'feedback': ''})
    return choices, True


def _parse_item(item):
    """Parse one QTI ``<item>``. Returns ``(question_dict, skip_reason)``."""
    ident = item.get('ident') or ''
    raw_type = _meta_field(item, 'question_type')
    if raw_type is None:
        return None, 'no question_type'
    if raw_type not in QTI_TYPE_MAP or QTI_TYPE_MAP[raw_type] is None:
        return None, f'unsupported type: {raw_type}'

    qtype = QTI_TYPE_MAP[raw_type]
    points_raw = _meta_field(item, 'points_possible')
    try:
        points = float(points_raw) if points_raw else 1.0
    except ValueError:
        points = 1.0

    choices, _ok = _parse_choices(item, qtype)
    # Auto-graded types need a parseable answer key. If none was extracted — e.g. a numerical
    # question scored by a <vargte>/<varlte> range we don't support — skip it with a reason
    # rather than importing a question that marks every student wrong.
    if qtype in _KEYED_TYPES and not any(c.get('isCorrect') for c in choices):
        return None, f'no correct answer parsed for {qtype} (e.g. numerical range or unsupported scoring)'
    question = {
        'ident': ident,
        'type': qtype,
        'text': _question_stem(item),
        'points': points,
        'choices': choices,
        'metadata': {'canvas_ident': ident, 'canvas_type': raw_type},
    }
    return question, None


def _assessment_title(root, default: str) -> str:
    assessment = _first(root, 'assessment')
    if assessment is not None and assessment.get('title'):
        return assessment.get('title')
    objbank = _first(root, 'objectbank')
    if objbank is not None and objbank.get('title'):
        return objbank.get('title')
    return default


def _content_sig(question: dict) -> tuple:
    """A content signature for dedup. Canvas exports often include the same question
    in multiple files (e.g. a quiz assessment and a question bank) with *different*
    idents, so deduping by ident alone leaves duplicates — dedup by content instead."""
    choices = tuple(sorted(
        ((c.get('text') or '').strip(), bool(c.get('isCorrect'))) for c in question.get('choices', [])
    ))
    return (question['type'], (question.get('text') or '').strip(), choices)


def _parse_document(xml_bytes: bytes, default_title: str, result: dict) -> None:
    """Parse one QTI XML document, appending questions/quizzes/skips to ``result``."""
    try:
        root = fromstring(xml_bytes)
    except Exception as e:  # not valid XML — record and move on
        result['skipped'].append({'ident': default_title, 'reason': f'parse error: {e}'})
        return

    items = list(_iter(root, 'item'))
    if not items:
        return

    is_assessment = _first(root, 'assessment') is not None
    title = _assessment_title(root, default_title)

    question_idents: list[str] = []
    for item in items:
        question, skip_reason = _parse_item(item)
        if skip_reason:
            result['skipped'].append({'ident': item.get('ident') or '', 'reason': skip_reason})
            continue
        sig = _content_sig(question)
        canonical = result['_sig_to_ident'].get(sig)
        if canonical is not None:
            # Same content already imported — reference the first occurrence so a quiz
            # that re-lists a bank question doesn't create a duplicate.
            question_idents.append(canonical)
            continue
        result['_sig_to_ident'][sig] = question['ident']
        result['questions'].append(question)
        question_idents.append(question['ident'])

    if is_assessment and question_idents:
        result['quizzes'].append({'title': title, 'question_idents': question_idents})


def parse_canvas_export(data) -> dict:
    """Parse a Canvas QTI export.

    ``data`` may be raw ``bytes``, a file path, or a binary file-like object. The
    export is normally a zip (Common Cartridge); a single bare QTI XML is also
    accepted.

    Returns::

        {
          'questions': [ {ident, type, text, points, choices, metadata}, ... ],
          'quizzes':   [ {title, question_idents:[ident, ...]}, ... ],
          'skipped':   [ {ident, reason}, ... ],
        }
    """
    if hasattr(data, 'read'):
        data = data.read()
    if isinstance(data, bytes):
        buffer = io.BytesIO(data)
    else:  # path string
        with open(data, 'rb') as fh:
            buffer = io.BytesIO(fh.read())

    result: dict = {'questions': [], 'quizzes': [], 'skipped': [], '_sig_to_ident': {}}

    try:
        with zipfile.ZipFile(buffer) as zf:
            # Sort so dedup keeps a deterministic canonical occurrence regardless of the
            # archive's internal member order (which varies by zip tooling / filesystem).
            xml_names = sorted(n for n in zf.namelist() if n.lower().endswith('.xml'))
            # Skip the manifest and Canvas meta files — they hold no QTI items.
            for name in xml_names:
                base = name.rsplit('/', 1)[-1].lower()
                if base in ('imsmanifest.xml', 'assessment_meta.xml') or base.endswith('_meta.xml'):
                    continue
                _parse_document(zf.read(name), default_title=base[:-4], result=result)
    except zipfile.BadZipFile:
        # Not a zip — treat the upload as a single QTI XML document.
        _parse_document(buffer.getvalue(), default_title='Imported Quiz', result=result)

    result.pop('_sig_to_ident', None)
    return result
