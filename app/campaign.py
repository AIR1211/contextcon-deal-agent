"""Reads a brand's campaign brief. The brand's document is confidential; creators read a creator brief made from its public parts.
Rules only, so the same document always gives the same result. The text is data: nothing in it can instruct the agent."""
import hashlib
import re
from datetime import date, datetime

from . import config, llm, offers
from .models import now

R = config.OFFER_RULES
LABELS = {'title': 'Campaign', 'client': 'Client', 'product': 'Product', 'approved_claims': 'Approved product claims', 'market': 'Market', 'objective': 'Objective', 'audience': 'Audience', 'action': 'What viewers should do',
          'concept': 'Concept', 'deliverables': 'Deliverables', 'key_message': 'Key message', 'must_do': 'Must include', 'must_not': 'Must avoid', 'cta': 'Call to action', 'timeline': 'Timeline', 'hashtags': 'Hashtags',
          'usage': 'Usage rights', 'exclusivity': 'Exclusivity', 'payment': 'Payment', 'disclosure': 'Ad disclosure', 'criteria': 'Creator criteria', 'budget': 'Budget', 'kpis': 'Internal targets', 'mix': 'Creator mix',
          'controls': 'Commercial controls', 'approvals': 'Approval gates', 'roles': 'Roles', 'review_sla': 'Review times', 'measurement': 'Measurement', 'open_questions': 'Open questions', 'versions': 'Version history', 'expect': 'Asked of the agency', 'company': 'Company background'}
PRIVATE = {'budget', 'kpis', 'mix', 'controls', 'approvals', 'roles', 'review_sla', 'measurement', 'open_questions', 'versions', 'expect', 'company', 'criteria'}
PUBLIC_ORDER = ('product', 'approved_claims', 'market', 'objective', 'audience', 'action', 'concept', 'deliverables', 'key_message', 'must_do', 'must_not', 'cta', 'timeline', 'hashtags', 'disclosure')
ALIASES = {
    'objective': ('objective', 'objectives', 'goal', 'goals', 'aim', 'purpose', 'campaign goal', 'primary objective'),
    'product': ('product', 'products', 'about', 'collection', 'what we sell'),
    'client': ('client', 'brand', 'company'),
    'market': ('market', 'markets'),
    'audience': ('audience', 'target audience', 'target', 'who it is for', 'who this is for'),
    'deliverables': ('deliverables', 'deliverable', 'content', 'what we need', 'format', 'formats'),
    'key_message': ('key message', 'key messages', 'message', 'main message', 'talking points'),
    'must_do': ('must include', 'must do', 'dos', 'do', 'please include', 'requirements', 'mandatory', 'include'),
    'must_not': ('do not', "don't", 'dont', 'donts', "don'ts", 'avoid', 'must not', 'never', 'not allowed'),
    'timeline': ('timeline', 'dates', 'date', 'deadline', 'go live', 'go live by', 'post by', 'live by', 'schedule', 'launch date', 'campaign window'),
    'hashtags': ('hashtags', 'hashtag', 'tags'),
    'usage': ('usage', 'usage rights', 'rights', 'licence', 'license'),
    'exclusivity': ('exclusivity', 'exclusive'),
    'payment': ('payment', 'payment terms'),
    'disclosure': ('disclosure', 'ad disclosure'),
    'budget': ('budget', 'fee', 'rate', 'rates', 'execution budget'),
}
LOOKUP = {a: k for k, names in ALIASES.items() for a in names}
# Long-form section titles. A line opens a section if it starts with one of these, after any numbering.
SECTIONS = (('claims that must not appear', 'must_not'), ('content restrictions', 'must_not'), ('required message points', 'key_message'), ('creator selection criteria', 'criteria'), ('selection criteria', 'criteria'),
            ('approval gates', 'approvals'), ('client roles', 'roles'), ('open questions', 'open_questions'), ('campaign timeline', 'timeline'), ('review and approval', 'review_sla'), ('baseline creator deliverables', 'deliverables'),
            ('target audience', 'audience'), ('product summary', 'product'), ('campaign concept', 'concept'), ('campaign objectives', 'kpis'), ('targets are not warranties', 'kpis'), ('budget ceiling', 'budget'), ('approved campaign execution cap', 'budget'),
            ('commercial controls', 'controls'), ('version history', 'versions'), ('document control', 'versions'), ('authoritative version', 'versions'), ('measurement', 'measurement'), ('attribution limitation', 'measurement'), ('requested creator mix', 'mix'),
            ('company background', 'company'), ('desired audience action', 'action'), ('what we expect', 'expect'), ('agency response', 'expect'), ('operating note', 'expect'), ('campaign at a glance', 'glance'), ('prepared for', 'expect'))
HEADER_CELLS = {'field', 'deliverable', 'product area', 'dimension', 'objective', 'milestone', 'creator segment', 'cost category', 'stage', 'role', 'metric', 'id', 'version'}
ESSENTIAL = ('objective', 'deliverables', 'key_message', 'timeline')
HEADING = re.compile(r"^[#*\s]*([A-Za-z][A-Za-z /&'’-]{0,34}?)[*\s]*(?::|\s[-–]\s)\s*(.*)$")
BARE = re.compile(r"^[#*\s]*([A-Za-z][A-Za-z /&'’-]{0,34}?)[*\s:]*$")
BULLET = re.compile(r'^\s*(?:[-*•]|\d+[.)])\s+(.*)$')
MONEY = re.compile(r'(?:₹|\brs\.?\s*|\binr\s*)([\d,]+(?:\.\d+)?)\s*(lakh|lac|crore|cr|k)?\b', re.I)
MONEY_TALK = re.compile(r'₹|\brs\.?\s*\d|\binr\s*\d|\bbudget\b|\blakh\b|\bcrore\b|\bexecution cap\b', re.I)
PROSE = {
    'objective': r'\b(?:we want to|our goal is|the goal is|aim to|looking to|hoping to|want to (?:get|drive|reach|build)|need to)\b',
    'audience': r"\b(?:targeting|aimed at|audience|for (?:women|men|students|parents|gen z|young)|(?:women|men|girls|guys|students|moms|parents)\s+(?:aged\s+)?\d{2})\b",
    'must_not': r"\b(?:do not|don't|dont|avoid|never|no claims?|no mention)\b",
    'must_do': r'\b(?:must|make sure|please (?:show|include|mention|tag|say|talk)|should (?:show|mention|include))\b',
    'key_message': r'\b(?:mention|highlight|talk about|focus on|key message|main thing|the message)\b',
    'deliverables': r'\b(?:reels?|stor(?:y|ies)|shorts?|videos?)\b',
    'timeline': r'\b(?:go live|post by|live (?:by|before)|deadline|(?:by|before|till|until) (?:the )?\d{1,2}(?:st|nd|rd|th)? [A-Za-z]{3,9}|(?:by|before|till|until) [A-Z][a-z]{2,8} \d{1,2}|(?:by|before|till|until)\s+(?:the\s+)?(?:end of\s+)?(?:next\s+)?[A-Za-z]{3,}|next (?:week|month))\b',
}
WORD_NUMBERS = {'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6}
# A default the agent can propose for a common open question. Anything else needs the brand's answer.
QUESTION_DEFAULTS = (
    (r'tax', 'Treat taxes as extra to the cap and show both views.', False),
    (r'fee|billing', "Avuno's fee is a disclosed 5% from each side, on closed deals only, kept outside the cap.", False),
    (r'activat', 'Needs the brand to define it before launch. It does not block signing.', False),
    (r'test account|access', 'Creators need access before work starts. If not, use a recorded demo.', False),
    (r'usage|rights', 'Organic use only, unless paid usage is priced separately. It blocks only a deal that includes paid ads.', False),
    (r'approver|backup', 'Ask the brand to name a backup. Approvals wait until then.', False),
)


def extract_pdf(data: bytes, max_pages: int = 60) -> dict:
    """Turns a PDF into plain lines. Table rows become 'a | b | c'. Repeated headers and footers are removed."""
    import pymupdf
    try:
        doc = pymupdf.open(stream=data, filetype='pdf')
    except Exception as e:
        raise ValueError('This file could not be read as a PDF.') from e
    if doc.is_encrypted:
        raise ValueError('This PDF is password protected.')
    if len(doc) > max_pages:
        raise ValueError(f'This PDF has more than {max_pages} pages.')
    pages = []
    for page in doc:
        items = []
        tables = page.find_tables().tables
        for table in tables:
            for row in table.rows:
                # Reads each cell by its box: table.extract() can scramble letters joined by ligatures.
                cells = [page.get_textbox(c) if c else None for c in row.cells]
                y, filled = row.bbox[1], [c.strip() for c in cells if c and c.strip()]
                if len(filled) == 1 and '\n' in filled[0]:      # A callout box: a title with its text underneath.
                    head, body = filled[0].split('\n', 1)
                    items += [(y, head.strip()), (y + .1, re.sub(r'\s*\n\s*', ' ', body).strip())]
                elif filled:
                    items.append((y, ' | '.join(re.sub(r'\s*\n\s*', ' ', c).strip() for c in filled)))
        for x0, y0, x1, y1, text, _, kind in page.get_text('blocks'):
            if kind != 0 or any(b[0] <= (x0 + x1) / 2 <= b[2] and b[1] <= (y0 + y1) / 2 <= b[3] for b in (t.bbox for t in tables)):
                continue
            merged: list[str] = []
            for raw in text.split('\n'):
                line = raw.strip()
                if not line:
                    continue
                if re.match(r'^[-•·▪●◦]', line):
                    merged.append('- ' + re.sub(r'^[-•·▪●◦]\s*', '', line))
                elif merged and (merged[-1] == '- ' or (len(merged[-1]) > 60 and not re.search(r'[.:!?]$', merged[-1]))):
                    merged[-1] = (merged[-1] + ' ' + line).replace('-  ', '- ')
                else:
                    merged.append(line)
            items += [(y0 + n / 100, line) for n, line in enumerate(merged)]
        pages.append([t for _, t in sorted(items, key=lambda i: i[0])])
    counts: dict[str, int] = {}
    for lines in pages:
        for key in {re.sub(r'\d+', '#', l) for l in lines}:
            counts[key] = counts.get(key, 0) + 1
    repeated = {k for k, n in counts.items() if len(pages) > 1 and n >= max(2, len(pages) / 2)}
    text = '\n\n'.join('\n'.join(l for l in lines if re.sub(r'\d+', '#', l) not in repeated) for lines in pages).strip()
    if len(text) < 30:
        raise ValueError('No readable text was found. Scanned PDFs are not supported yet.')
    return {'text': text, 'pages': len(pages)}


def _nice_title(raw: str, text: str) -> str:
    """An all-caps heading in normal case, keeping the spelling the document uses elsewhere (OrbitDesk, not Orbitdesk)."""
    def word(w):
        if not w.isupper() or len(w) < 3:
            return w
        return next((m for m in re.findall(rf'\b{re.escape(w)}\b', text, re.I) if not m.isupper() and not m.islower() and m != m.title()), w.title())
    return ' '.join(word(w) for w in raw.split())


def _key(name: str) -> str | None:
    return LOOKUP.get(name.strip().lower().replace('’', "'"))


def _section(line: str) -> str | None:
    if len(line) > 80 or '|' in line:
        return None
    normal = re.sub(r'^\d+(?:\.\d+)?\s*/?\s*', '', line).strip().lower().replace('’', "'")
    return next((key for phrase, key in SECTIONS if normal.startswith(phrase)), None)


def _dates(text: str) -> list[date]:
    out = []
    for m in re.finditer(r'\b(\d{1,2})\s+([A-Za-z]{3,9})\.?,?\s+(20\d{2})\b|\b([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s+(20\d{2})\b|\b(20\d{2})-(\d{2})-(\d{2})\b', text):
        try:
            if m[1]:
                out.append(datetime.strptime(f'{m[1]} {m[2][:3]} {m[3]}', '%d %b %Y').date())
            elif m[4]:
                out.append(datetime.strptime(f'{m[5]} {m[4][:3]} {m[6]}', '%d %b %Y').date())
            else:
                out.append(date(int(m[7]), int(m[8]), int(m[9])))
        except ValueError:
            continue
    return out


def _amount(text: str) -> int | None:
    m = MONEY.search(text.replace(' ', ' '))
    if not m:
        return None
    return round(float(m[1].replace(',', '')) * {'k': 1000, 'lakh': 100000, 'lac': 100000, 'crore': 10000000, 'cr': 10000000}.get((m[2] or '').lower(), 1))


def _per_creator(text: str) -> int | None:
    m = re.search(r'\b(\d+|one|two|three|four|five|six)\s+per creator', text, re.I)
    return (int(m[1]) if m[1].isdigit() else WORD_NUMBERS[m[1].lower()]) if m else None


def parse(text: str) -> dict:
    """Returns each field with the line it came from, plus flags and what's missing. Never invents a value."""
    lines = (text or '').replace('\r', '').split('\n')
    found: dict[str, list] = {}
    budget = {'cap': None, 'pool': None, 'creators_target': None}
    reels = stories = None
    questions, versions = [], []

    def add(key, value, line):
        value = value.strip().strip('*').strip()
        if value:
            found.setdefault(key, []).append((value, line))

    def table_row(cells, i, section):
        nonlocal reels, stories
        first = cells[0].strip().lower()
        if first in HEADER_CELLS:
            return
        if re.fullmatch(r'q\d+', first) and len(cells) >= 2:
            questions.append({'id': cells[0], 'question': cells[1], 'asked': cells[2] if len(cells) > 2 else '', 'line': i})
            add('open_questions', f'{cells[0]}: {cells[1]}', i)
            return
        if re.fullmatch(r'v\d+(\.\d+)*', first):
            versions.append({'version': cells[0], 'status': cells[-1], 'line': i})
            add('versions', ' | '.join(cells), i)
            return
        rest = ' | '.join(cells[1:])
        if section == 'glance' or section is None:
            if first == 'creator requirement':
                m = re.search(r'(\d+)\s+creators', rest)
                budget['creators_target'] = int(m[1]) if m else budget['creators_target']
                add('mix', rest, i)
            elif first == 'document version':
                add('versions', rest, i)
            elif _key(first):
                add(_key(first), rest, i)
            return
        if section == 'deliverables':
            add('deliverables', f'{cells[0]}: {cells[1]}' + (f' ({cells[2]})' if len(cells) > 2 else ''), i)
            if re.search(r'short[- ]form|reel|video', first):
                reels = _per_creator(rest) or reels
            if re.search(r'stor(?:y|ies)', first):
                stories = _per_creator(rest) or stories
        elif section == 'product':
            add('approved_claims', f'{cells[0]}: {rest}', i)
        elif section == 'budget':
            add('budget', f'{cells[0]}: {rest}', i)
            amount = _amount(rest)
            if 'creator' in first and amount:
                budget['pool'] = amount
                m = re.search(r'(\d+)\s+creators', rest)
                budget['creators_target'] = int(m[1]) if m else budget['creators_target']
            if 'total' in first and amount:
                budget['cap'] = amount
        else:
            add(section, f'{cells[0]}: {rest}', i)

    section, long_form, first = None, False, True
    for i, raw in enumerate(lines):
        line = raw.strip()
        if not line:
            continue
        bullet = BULLET.match(line)
        cells = [c.strip() for c in line.split(' | ')] if ' | ' in line else None
        heading = HEADING.match(line) if not bullet and not cells else None
        bare = BARE.match(line) if not bullet and not cells else None
        long_section = _section(line) if not bullet else None
        if long_section:
            section, long_form = long_section, True
            if long_section == 'budget':
                amount = _amount(line)
                budget['cap'] = amount or budget['cap']
                if amount:
                    add('budget', line, i)
        elif cells:
            table_row(cells, i, section)
        elif heading and _key(heading[1]):
            section, long_form = _key(heading[1]), False
            add(section, heading[2], i)
        elif bare and _key(bare[1]):
            section, long_form = _key(bare[1]), False
        elif first and not bullet:
            if len(line) <= 90 and not re.match(r'(hi|hey|hello|dear|greetings|namaste|good (morning|afternoon|evening))\b', line, re.I) and not re.search(r'[.!?,]$', line):
                add('title', line.lstrip('# '), i)
        elif bullet and section:
            add(section, bullet[1], i)
        elif section and long_form:
            if section not in ('glance',):
                add(section, line, i)
        elif section and raw[:1] in (' ', '\t'):
            add(section, line, i)
        else:
            section = None
        first = False

    # Formal briefs name the campaign on the line after "Campaign brief".
    for i, l in enumerate(lines[:8]):
        if re.search(r'campaign brief$', l.strip(), re.I):
            nxt = next((n for n in range(i + 1, min(i + 4, len(lines))) if lines[n].strip()), None)
            if nxt is not None:
                found['title'] = [(_nice_title(lines[nxt], text), nxt)]
            break

    # Unstructured briefs: look for the same details sentence by sentence.
    for i, raw in enumerate(lines):
        for sentence in re.split(r'(?<=[.!?])\s+', raw.strip()):
            for key, pattern in PROSE.items():
                if key in ('key_message', 'must_do') and re.search(PROSE['must_not'], sentence, re.I):
                    continue      # "Don't mention X" is a restriction, not a message.
                if key == 'key_message' and any(sentence == v for v, _ in found.get('must_do', [])):
                    continue
                # Short messages can say several things of one kind. Long documents state them under headings.
                if (key not in found or (len(lines) < 30 and key in ('must_do', 'must_not') and not any(sentence == v for v, _ in found[key]))) and ' | ' not in sentence and re.search(pattern, sentence, re.I):
                    add(key, sentence, i)

    x = offers.extract(text or '')
    b = llm.parse_brief_rules(text or '')
    reels, stories = reels or b['reels'], stories or b['stories']

    def line_of(pattern):
        return next((i for i, l in enumerate(lines) if re.search(pattern, l, re.I)), None)

    if 'deliverables' not in found and (b['reels'] or b['stories']):
        parts = [f"{b['reels']} reel(s)" if b['reels'] else '', f"{b['stories']} stories" if b['stories'] else '']
        add('deliverables', ', '.join(p for p in parts if p), line_of(r'reel|stor(?:y|ies)'))
    tags = sorted(set(re.findall(r'#\w+', text or '')), key=(text or '').find)
    if 'hashtags' not in found and tags:
        add('hashtags', ' '.join(tags), line_of(r'#\w+'))
    if 'usage' not in found and (x['usage_days'] or x['usage_perpetual']):
        add('usage', 'Forever' if x['usage_perpetual'] else f"{x['usage_days']} days", line_of(r'usage|rights|licen[cs]e|perpetu|forever'))
    if 'exclusivity' not in found and x['exclusivity_days']:
        add('exclusivity', f"{x['exclusivity_days']} days", line_of(r'exclusiv'))
    if 'payment' not in found and x['payment_days']:
        add('payment', f"{x['payment_days']} days", line_of(r'net\s*-?\s*\d|payment|paid|invoice'))
    if 'disclosure' not in found and re.search(r'#ad\b|paid partnership|\basci\b|disclos', text or '', re.I):
        i = line_of(r'#ad\b|paid partnership|\basci\b|disclos')
        add('disclosure', 'Clear paid partnership disclosure is required.', i)
    cta = re.search(r'approved cta:?\s*[“"]([^”"]+)[”"]', text or '', re.I)
    if cta:
        add('cta', cta[1], line_of(re.escape(cta[0][:20])))

    # Budget: the current cap and creator pool. Figures on superseded version lines are ignored.
    superseded = {v['line'] for v in versions if re.search(r'supersed|old|draft', v['status'], re.I)}
    if budget['cap'] is None:
        for i, l in enumerate(lines):
            if i not in superseded and ' | v' not in l and re.search(r'\bcap\b|execution budget|^budget\b', l, re.I) and _amount(l):
                budget['cap'] = _amount(l)
                break
    if budget['cap'] is None and 'budget' in found:
        budget['cap'] = llm._money(found['budget'][0][0])
    if budget['cap'] is None:
        budget['cap'] = next((llm._money(s) for s in re.split(r'(?<=[.!?])\s+', text or '') if re.search(r'\bbudget\b', s, re.I) and llm._money(s)), None)
    if budget['pool'] and budget['creators_target']:
        budget['per_creator'] = budget['pool'] // budget['creators_target']

    # Creator criteria stated as numbers.
    criteria = ' '.join(v for v, _ in found.get('criteria', []))
    limits: dict = {}
    m = re.search(r'([\d,]{4,})\s*[–-]\s*([\d,]{4,})\s*followers', criteria, re.I)
    if m:
        limits['followers'] = [int(m[1].replace(',', '')), int(m[2].replace(',', ''))]
    m = re.search(r'(\d+(?:\.\d+)?)\s*%\s*or higher|engagement[^.]*?(\d+(?:\.\d+)?)\s*%', criteria, re.I)
    if m:
        limits['engagement_pct'] = float(m[1] or m[2])
    m = re.search(r'at least\s*(\d+)\s*%\s*india', criteria, re.I)
    if m:
        limits['india_pct'] = int(m[1])
    limits['flexible_size'] = bool(re.search(r'smaller creators may be', criteria, re.I))

    fields = []
    for k in LABELS:
        if k in found:
            items = [v for v, _ in found[k]]
            fields.append({'key': k, 'label': LABELS[k], 'value': '; '.join(items), 'items': items, 'lines': sorted({l for _, l in found[k] if l is not None}), 'private': k in PRIVATE})

    flags = []

    def flag(severity, message, private=False):
        flags.append({'severity': severity, 'text': message, 'private': private})

    low = (text or '').lower()
    for pattern, why in offers.SCAMS:
        if re.search(pattern, low):
            flag('block', why)
    if x['no_disclosure']:
        flag('block', 'The brief asks to hide that this is paid. Ad disclosure is required, so this deal stops.')
    if x['usage_perpetual']:
        flag('warn', f"Asks for usage rights forever. The agreed terms apply instead, and our limit is {R['max_usage_days']} days.")
    elif x['usage_days'] and x['usage_days'] > R['max_usage_days']:
        flag('warn', f"Asks for {x['usage_days']} days of usage, above the {R['max_usage_days']}-day limit.")
    if x['exclusivity_days'] and x['exclusivity_days'] > R['max_exclusivity_days']:
        flag('warn', f"Asks for {x['exclusivity_days']} days of exclusivity, above the {R['max_exclusivity_days']}-day limit.")
    if x['payment_days'] and x['payment_days'] > R['max_payment_days']:
        flag('warn', f"Pays in {x['payment_days']} days, above the {R['max_payment_days']}-day limit. Funds are held upfront instead.")
    if x['unlimited_revisions']:
        flag('warn', f"Asks for unlimited revisions. The contract allows up to {R['max_revisions']} rounds.")
    if x['barter_only']:
        flag('warn', 'Offers product or exposure, not money.')
    if 'disclosure' not in found:
        flag('info', "Doesn't mention ad disclosure. The contract requires it anyway.")
    if budget['cap'] or MONEY_TALK.search(text or ''):
        flag('info', 'Budget figures stay private. Creators only see the creator brief.', private=True)
    current = next((v for v in versions if re.search(r'current', v['status'], re.I)), None)
    if superseded and current:
        flag('info', f"Using {current['version']}, the current version. Figures from superseded versions are ignored.", private=True)
    timeline_text = ' '.join(v for v, _ in found.get('timeline', []))
    passed = [d for d in _dates(timeline_text) if d < date.today()]
    if passed:
        flag('warn', f'A date in the timeline has already passed: {passed[0].isoformat()}.')
    if re.search(r'synthetic test|fictional company', low):
        flag('info', 'This document says it is fictional, written for testing.')
    open_questions = []
    for q in questions:
        default = next(((d, blocks) for pattern, d, blocks in QUESTION_DEFAULTS if re.search(pattern, q['question'], re.I)), ("Needs the brand's answer.", True))
        open_questions.append({'id': q['id'], 'question': q['question'], 'default': default[0], 'blocks': default[1], 'line': q['line']})
    if open_questions:
        flag('warn', f'{len(open_questions)} questions in this brief are unanswered. Proposed defaults are listed, and none are assumed silently.', private=True)
    parsed = {'text': text, 'sha': hashlib.sha256((text or '').encode('utf8')).hexdigest(), 'fields': fields, 'flags': flags, 'missing': [LABELS[k] for k in ESSENTIAL if k not in found], 'read_at': now(), 'reels': reels, 'stories': stories,
              'budget': budget, 'limits': limits, 'open_questions': open_questions, 'version': current['version'] if current else None, 'approvals': [v for v, _ in found.get('approvals', [])]}
    parsed['creator_brief'] = creator_brief(parsed)
    return parsed


def creator_brief(parsed: dict) -> dict:
    """What creators read: only public fields, and any line that talks about money is removed."""
    by = {f['key']: f for f in parsed['fields']}
    sections = []
    for key in PUBLIC_ORDER:
        if key in by:
            items = [i for i in by[key]['items'] if not MONEY_TALK.search(i)]
            if items:
                sections.append({'key': key, 'label': LABELS[key], 'items': items})
    return {'title': by['title']['value'] if 'title' in by else 'Campaign brief', 'client': re.sub(r'\s*\(.*?\)\s*', ' ', by['client']['value']).strip() if 'client' in by else '', 'version': parsed.get('version'), 'sections': sections}


def public(brief: dict | None) -> dict | None:
    """The view anyone can see: no original text, budget, internal targets, roles or open questions."""
    if not brief:
        return None
    return {'sha': brief['sha'], 'read_at': brief.get('read_at'), 'is_mock': brief.get('is_mock', False), 'version': brief.get('version'), 'creator_brief': brief['creator_brief'], 'missing': brief['missing'],
            'fields': [f for f in brief['fields'] if not f.get('private')], 'flags': [f for f in brief['flags'] if not f.get('private')], 'reels': brief.get('reels'), 'stories': brief.get('stories')}


def check_creator(brief: dict | None, creator: dict) -> list[dict]:
    """Checks a creator against the brief's own criteria. Missing data is Unknown, never a failure."""
    limits = (brief or {}).get('limits') or {}
    s = creator.get('stats') or {}
    out = []
    if limits.get('followers'):
        lo, hi = limits['followers']
        f = s.get('followers')
        status = 'unknown' if f is None else 'pass' if lo <= f <= hi else 'partial' if f < lo and limits.get('flexible_size') else 'fail'
        out.append({'label': f'Audience {lo // 1000}K-{hi // 1000}K', 'status': status, 'detail': f'{int(f):,} followers' if f is not None else 'Not read'})
    if limits.get('engagement_pct') is not None:
        er = None if s.get('engagement_anomalous') else s.get('engagement_rate')
        status = 'unknown' if er is None else 'pass' if er * 100 >= limits['engagement_pct'] else 'fail'
        out.append({'label': f"Engagement {limits['engagement_pct']:g}%+", 'status': status, 'detail': f'{round(er * 100 + 1e-9, 1)}%' if er is not None else 'Not reliable yet'})
    if limits.get('india_pct') is not None:
        aud = creator.get('audience_country_pct')
        status = 'unknown' if aud is None else 'partial' if aud >= limits['india_pct'] else 'fail'
        out.append({'label': f"India audience {limits['india_pct']}%+", 'status': status, 'detail': f'{aud}%, self-reported' if aud is not None else 'Not provided'})
    return out


def placeholder(company: dict) -> dict:
    """Simulated deals with a brand that has no brief use this. It's labelled as mock everywhere it appears."""
    name, niche = company.get('name') or 'This brand', company.get('niche') or 'its products'
    text = f"Placeholder brief for {name} (mock)\nObjective: Introduce {niche} to the creator's audience.\nKey message: Show how it fits into everyday life.\nDeliverables: As agreed in the media pack.\nDisclosure: Mark as a paid partnership.\nTimeline: To be agreed."
    return {**parse(text), 'is_mock': True}


def must_lines(brief: dict) -> tuple[str, str]:
    by_key = {f['key']: f['value'] for f in brief.get('fields', [])}
    return by_key.get('must_do') or by_key.get('key_message', ''), by_key.get('must_not', '')
