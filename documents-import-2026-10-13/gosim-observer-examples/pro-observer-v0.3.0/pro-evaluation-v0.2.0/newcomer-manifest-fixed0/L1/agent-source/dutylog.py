"""Deterministic public duty-log decoding and causal event store (F15/F16/F18).

normalize(text)      -> NFKC, zero-width chars removed
decode_morse(line)   -> list of (span_text, decoded) for runs of two-glyph Morse
decode_solfege(line) -> list of (span_text, decoded) for "re do : mi 休止" style times
decode_caesar(line, hint_shift) -> (shift, decoded) or None for Latin segments that read as English
annotate(text, day)  -> text with "⟨解码:…⟩" appended to every decoded line
"""
import re
import unicodedata
import os
from datetime import datetime, timedelta, timezone
from bisect import bisect_left

ZERO_WIDTH = dict.fromkeys(map(ord, "​‌‍⁠﻿"), None)


def normalize(text: str) -> str:
    return unicodedata.normalize("NFKC", text).translate(ZERO_WIDTH)


MORSE = {
    ".-": "A", "-...": "B", "-.-.": "C", "-..": "D", ".": "E", "..-.": "F", "--.": "G", "....": "H", "..": "I",
    ".---": "J", "-.-": "K", ".-..": "L", "--": "M", "-.": "N", "---": "O", ".--.": "P", "--.-": "Q", ".-.": "R",
    "...": "S", "-": "T", "..-": "U", "...-": "V", ".--": "W", "-..-": "X", "-.--": "Y", "--..": "Z",
    "-----": "0", ".----": "1", "..---": "2", "...--": "3", "....-": "4", ".....": "5", "-....": "6",
    "--...": "7", "---..": "8", "----.": "9", "-..-.": "/", "-....-": "-", "---...": ":", ".-.-.-": ".",
    "--..--": ",", "-.--.": "(", "-.--.-": ")", "..--..": "?",
}
# glyph pairs seen in A1-D1 plus plausible variants (symbol a, symbol b); which one is the dot is decided per run
GLYPHS = [("○", "●"), ("ti", "TA"), ("di", "DA"), ("dit", "dah"), ("短", "长"), ("短", "長"), ("嘀", "嗒"),
          ("滴", "答"), ("♪", "♫"), ("·", "—"), ("・", "ー"), (".", "-"), ("•", "—"), ("•", "-"), ("·", "-")]
TIME_HINT = re.compile(r"\d{1,2}/\d{1,2}|\d{3,4}|\d{1,2}:\d{2}")


def _runs(line: str, a: str, b: str):
    tok = f"(?:{re.escape(a)}|{re.escape(b)})+"
    run = re.compile(f"{tok}(?:[ 　]+(?:/[ 　]+)?{tok}){{2,}}")
    return list(run.finditer(line))


def _split_symbols(token: str, a: str, b: str):
    out, i = [], 0
    while i < len(token):
        if token.startswith(a, i):
            out.append(0); i += len(a)
        elif token.startswith(b, i):
            out.append(1); i += len(b)
        else:
            return None
    return out


def decode_morse(line: str):
    found = []
    for a, b in GLYPHS:
        for m in _runs(line, a, b):
            span = m.group(0)
            words = re.split(r"[ 　]+/[ 　]+", span)
            best = None
            for dot in (0, 1):
                text, bad = [], 0
                for w in words:
                    letters = []
                    for t in w.split():
                        syms = _split_symbols(t, a, b)
                        if syms is None:
                            bad += 1; continue
                        code = "".join("." if s == dot else "-" for s in syms)
                        ch = MORSE.get(code)
                        if ch is None:
                            bad += 1; letters.append("?")
                        else:
                            letters.append(ch)
                    text.append("".join(letters))
                decoded = " ".join(text)
                score = (-bad, len(TIME_HINT.findall(decoded)))
                if best is None or score > best[0]:
                    best = (score, decoded)
            if best and best[0][0] == 0:
                found.append((span, best[1]))
    # drop runs contained in a longer accepted run (e.g. ○● and ●○ alternations)
    found.sort(key=lambda x: -len(x[0]))
    kept = []
    for span, dec in found:
        if not any(span in k for k, _ in kept):
            kept.append((span, dec))
    return kept


SOLFEGE = {"高音do": "8", "高音re": "9", "do": "1", "re": "2", "mi": "3", "fa": "4", "sol": "5", "so": "5",
           "la": "6", "si": "7", "ti": "7", "休止": "0", "休": "0"}
_SYL = "高音do|高音re|sol|do|re|mi|fa|so|la|si|ti|休止|休"
SOLF_RUN = re.compile(rf"(?<![A-Za-z])(?:{_SYL})(?:[ 　]*(?::|：)?[ 　]*(?:{_SYL}))+(?![A-Za-z])")


def decode_solfege(line: str):
    out = []
    for m in SOLF_RUN.finditer(line):
        span = m.group(0)
        if ":" not in span and "：" not in span:
            continue
        parts = re.split(r"[:：]", span)
        digits = []
        for p in parts:
            syl = re.findall(_SYL, p)
            digits.append("".join(SOLFEGE[s] for s in syl))
        if all(digits) and all(len(d) <= 2 for d in digits):
            out.append((span, ":".join(d.zfill(2) for d in digits)))
    return out


EN_WORDS = set("""the a an at to is of and in on for from by be will are was it this that so please report reported fault
camera guider guide moves move moved every frame frames point until data dead local time utc tonight night flat
flats test tests lamp cover mirror segments segment no not do don't wind windy closed close dome sky thin cloud clouds
haze rain observe observable fine ok okay usable after before hours hour minutes minute engineering notice note with
than up down mountain ridge degrees deg zenith distance south north east west southeast southwest northeast northwest
sector region forecast cooling unstable launch window rocket maintenance power outage earthquake quake drop efficiency
shutter focus tomorrow today morning evening midnight again late early start end starts ends between broken fix fixed
request requests target targets field fields mirror coating hydraulic oil""".split())


def _shift(text: str, k: int) -> str:
    out = []
    for ch in text:
        if "a" <= ch <= "z":
            out.append(chr((ord(ch) - 97 - k) % 26 + 97))
        elif "A" <= ch <= "Z":
            out.append(chr((ord(ch) - 65 - k) % 26 + 65))
        else:
            out.append(ch)
    return "".join(out)


def _en_score(text: str) -> int:
    return sum(w.lower() in EN_WORDS for w in re.findall(r"[A-Za-z']+", text))


LATIN_SEG = re.compile(r"[A-Za-z][A-Za-z0-9 ,.:;'()/\-]{15,}")


def decode_caesar(line: str, hint_shift: int | None = None):
    """Decode Latin segments that read as English after a Caesar back-shift (shift = letters moved forward)."""
    out = []
    for m in LATIN_SEG.finditer(line):
        seg = m.group(0)
        if len(re.findall(r"[A-Za-z]{2,}", seg)) < 4:
            continue
        scores = [(_en_score(_shift(seg, k)), k) for k in range(26)]
        base = scores[0][0]
        best_score, best_k = max(scores)
        if hint_shift is not None and scores[hint_shift % 26][0] >= best_score - 1:
            best_score, best_k = scores[hint_shift % 26][0], hint_shift % 26
        if best_k != 0 and best_score >= 3 and best_score > base + 1:
            out.append((seg, best_k, _shift(seg, best_k)))
    return out


def annotate(text: str, day_of_month: int) -> tuple[str, dict]:
    """Return normalised text with decoded annotations, and counters of what was decoded."""
    stats = {"morse": 0, "solfege": 0, "caesar": 0}
    lines = []
    for line in normalize(text).split("\n"):
        notes = []
        key = re.search(r"(?:钥匙|鑰匙|key|ずらし|偏移|位移)\D{0,8}(\d{1,2})", line)
        hint = int(key.group(1)) if key else day_of_month
        for span, dec in decode_morse(line):
            notes.append(f"摩斯→{dec}"); stats["morse"] += 1
        for span, dec in decode_solfege(line):
            notes.append(f"唱名「{span}」→{dec}"); stats["solfege"] += 1
        for seg, k, dec in decode_caesar(line, hint):
            notes.append(f"凯撒(位移{k})→{dec}"); stats["caesar"] += 1
        lines.append(line + ("  ⟨解码: " + " | ".join(notes) + "⟩" if notes else ""))
    return "\n".join(lines), stats


_TRAD = str.maketrans("東邊頂場鏡蓋時裡裏後報廢說實測關傳聞試驗", "东边顶场镜盖时里里后报废说实测关传闻试验")
_DIR = {"东北": 45., "东南": 135., "西南": 225., "西北": 315.,
        "北东": 45., "南东": 135., "南西": 225., "北西": 315.,
        "北": 0., "东": 90., "南": 180., "西": 270.}
_DIR_RE = r"东北|东南|西南|西北|北东|南东|南西|北西|北|东|南|西"
_NUM = r"[零〇一二两三四五六七八九十\d]+"
_CLOCK = re.compile(rf"(?<!\d)({_NUM})(?::(\d{{1,2}})|[点时]({_NUM})?分?([半整])?)")
_DATE = re.compile(r"(?<!\d)(\d{1,2})\s*[/月]\s*(\d{1,2})(?:日)?")
_BAD = re.compile(r"隔壁|邻の|隣の|別の山|传闻|听说|有人说|没确认|未确认|别当真|不当真|rumou?r|other site", re.I)
_FLAT = re.compile(r"平场|镜盖|フラット|flat[- ]?(?:lamp|field|test)|lens[- ]?cap", re.I)
_FAULT = re.compile(r"导星相机|ガイドカメラ|guider|吞吐量.*(?:掉|只剩)|效率.*下降", re.I)


def _number(s):
    if not s:
        return 0
    if s.isdigit():
        return int(s)
    digits = {c: i for i, c in enumerate("零一二三四五六七八九")}
    digits.update({"〇": 0, "两": 2})
    if "十" in s:
        a, b = s.split("十", 1)
        return (digits.get(a, 1) * 10) + digits.get(b, 0)
    return digits.get(s, 0)


def _utc(value):
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc)
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _decoded(line, day):
    line = normalize(line).translate(_TRAD)
    for span, _, decoded in decode_caesar(line, day):
        line = line.replace(span, decoded)
    for span, decoded in decode_solfege(line):
        line = line.replace(span, decoded)
    for span, decoded in decode_morse(line):
        line = line.replace(span, decoded)
    # Remove only punctuation emoticons, preserving textual date/time parentheses.
    return re.sub(r"\([^A-Za-z0-9\u4e00-\u9fff]*\)", "", line)


class DutyLog:
    """All times are aware UTC datetimes. Never reads card identities or gold data.

    ingest(messages) must precede processing the exposure receipt. horizon() returns
    None until an actual text terrain announcement was seen, preserving old cards.
    Ambiguous fault lines remain unresolved and must not drive an automatic report.
    """
    def __init__(self, utc_offset_hours=0., min_alt=30., log=lambda text: None):
        self.offset = timedelta(hours=float(utc_offset_hours))
        self.min_alt = float(min_alt)
        self.log = log
        self.seen = set()
        self.terrain = {}  # (start az, end az) -> (altitude, padding, authority)
        self.events = {}
        self.flat_windows = []
        self.flat_starts = []
        self.unresolved = []
        self.version = 0
        self.superseded_faults = set()
        self.conditional_faults = {}
        self.fault_delay = timedelta(minutes=float(os.environ.get('V7_FAULT_LOG_DELAY_MIN', '15')))
        self.fault_retry_delay = timedelta(minutes=float(os.environ.get('V7_FAULT_LOG_RETRY_MIN', '30')))
        self.fault_min_sources = int(os.environ.get('V7_FAULT_LOG_MIN_SOURCES', '2'))
        if self.fault_delay < timedelta(0) or self.fault_retry_delay <= timedelta(0) or self.fault_min_sources < 1:
            raise ValueError('fault delay must be nonnegative, retry delay positive, source count at least one')
        self.fault_attempts = {}
        self.fault_aliases = {}
        self.cancelled_flat_starts = set()
        self.superseded_flat_windows = set()
        self.last_repair = None
        self.report_receipts = set()

    @property
    def has_terrain(self):
        return bool(self.terrain)

    def horizon(self, az):
        if not self.terrain:
            return None
        h = self.min_alt
        for (a, b), (alt, pad, _) in self.terrain.items():
            if (float(az) - a + pad) % 360 <= (b - a) % 360 + 2 * pad:
                h = max(h, alt)
        return h

    def overlaps_flat(self, start, end):
        start, end = _utc(start), _utc(end)
        i = bisect_left(self.flat_starts, end) - 1
        return i >= 0 and self.flat_windows[i][1] > start and end > start

    def clip_exposure(self, start, seconds):
        start = _utc(start)
        i = bisect_left(self.flat_starts, start)
        if i and self.flat_windows[i - 1][1] > start:
            return 0.
        if i < len(self.flat_windows):
            return max(0., min(float(seconds), (self.flat_windows[i][0] - start).total_seconds()))
        return float(seconds)

    def flat_end(self, now):
        now = _utc(now)
        i = bisect_left(self.flat_starts, now)
        if i < len(self.flat_windows) and self.flat_starts[i] == now:
            return self.flat_windows[i][1]
        return self.flat_windows[i - 1][1] if i and self.flat_windows[i - 1][1] > now else None

    def due_fault(self, now):
        """High parsing-confidence, free-only suggestion; never sends a report.

        Caller must enforce the free allowance and call mark_report for EVERY real
        report receipt, even when the report was generated by another detector.
        Confidence is a parser authority label, NOT a calibrated fault posterior.
        """
        now = _utc(now)
        eligible = [e for e in self.events.values() if e['kind'] == 'fault'
                    and e.get('confidence', 0) >= .9 and e.get('policy') == 'at_onset'
                    and len(e.get('sources', [])) >= self.fault_min_sources
                    and e['issued'] <= now and e['start'] + self.fault_delay <= now
                    and (self.last_repair is None or e['start'] > self.last_repair)]
        if not eligible:
            return None
        event = max(eligible, key=lambda e: e['start'])
        key = event['start'].isoformat()
        attempts, retry_at = self.fault_attempts.get(key, (0, event['start'] + self.fault_delay))
        if attempts >= 2 or now < retry_at:
            return None
        return dict(event, event_key=key, due_at=max(event['start'] + self.fault_delay, retry_at), attempts=attempts)

    def mark_report(self, result, now, event_key=None):
        """Record a real public report result; at most one retry per announcement."""
        if not isinstance(result, dict) or 'correct' not in result:
            return
        now = _utc(now)
        receipt = (now, bool(result['correct']))
        if receipt in self.report_receipts:
            return
        self.report_receipts.add(receipt)
        if event_key is not None:
            key = str(event_key)
            while key in self.fault_aliases:
                key = self.fault_aliases[key]
            count, _ = self.fault_attempts.get(key, (0, now))
            self.fault_attempts[key] = (min(2, count + 1), now + self.fault_retry_delay)
        if result['correct'] is True:
            self.last_repair = max(now, self.last_repair) if self.last_repair else now

    def _terrain(self, line):
        line = line.replace("落山", "落下")
        if _BAD.search(line) or not re.search(r"山|稜线|稜線|天顶距|对星|拿星|数字为准", line):
            return
        # Each clause can name another sector; do not mix weather directions later in the line.
        z = re.search(r"天顶距\D{0,10}(\d+(?:\.\d+)?)\s*[度°]", line)
        if z:
            dirs = list(re.finditer(_DIR_RE, line))
            if not dirs:
                return
            near = sorted(dirs, key=lambda m: min(abs(m.end()-z.start()), abs(m.start()-z.end())))[:2]
            near.sort(key=lambda m: m.start())
            first = near[0]
            second = near[1] if len(near) > 1 and re.fullmatch(r"(?:边)?(?:到|至|[-–~〜])", line[first.end():near[1].start()].strip()) else first
            a, b = _DIR[first.group()], _DIR[second.group()]
            alt, rank = 90. - float(z.group(1)), 3
        else:
            # Low-confidence approximate statements cannot override a measured value.
            mountain = re.search(r"山|稜线|稜線", line)
            if mountain:
                prefix_dirs = list(re.finditer(_DIR_RE, line[:mountain.start()]))
                if prefix_dirs:
                    line = line[prefix_dirs[-1].start():]
            m = re.search(rf"({_DIR_RE}).{{0,65}}?(\d+(?:\.\d+)?)\s*[度°]", line)
            if not m:
                d = re.search(_DIR_RE, line)
                if d:
                    key = (_DIR[d.group()], _DIR[d.group()])
                    self.terrain.setdefault(key, (40., 30., 0))
                return
            a = b = _DIR[m.group(1)]
            alt = float(m.group(2))
            rank = 1 if re.search(r"好像|大概|说不准", m.group()) else 2
        if not 0 <= alt < 90:
            return
        key = (a, b)
        old = self.terrain.get(key)
        if old is None or rank >= old[2]:
            self.terrain[key] = (alt, 25. if a == b else 15., rank)
            # An explicit range supersedes earlier rough single-direction notices inside it.
            if a != b:
                for k, v in list(self.terrain.items()):
                    if k[0] == k[1] and (k[0]-a) % 360 <= (b-a) % 360 and v[2] < rank:
                        del self.terrain[k]

    def _times(self, line, issued):
        local = issued + self.offset
        date_matches = list(_DATE.finditer(line))
        if not date_matches:
            if not re.search(r"今晚|明晚|昨晚|昨夜|刚才|today|tonight|tomorrow", line, re.I):
                return []
            day = local.replace(hour=0, minute=0, second=0, microsecond=0)
            day += timedelta(days=1 if re.search(r"明晚|tomorrow", line, re.I) else -1 if re.search(r"昨晚|昨夜", line) else 0)
        else:
            # Distinct explicit dates in a correction need a resolved reference, not a guess.
            dates = {(int(m[1]), int(m[2])) for m in date_matches}
            if len(dates) != 1:
                return []
            month, dom = next(iter(dates))
            candidates = []
            for year in (local.year-1, local.year, local.year+1):
                try:
                    candidates.append(datetime(year, month, dom, tzinfo=timezone.utc))
                except ValueError:
                    pass
            if not candidates:
                return []
            day = min(candidates, key=lambda t: abs((t-local).total_seconds()))
            weekday = re.search(r"(?:周|星期)([一二三四五六日天])", line)
            if weekday and "一二三四五六日".find(weekday[1].replace("天", "日")) != day.weekday():
                return []
        night = bool(re.search(r"当晚|那晚|晚上|夜里|夜间|の夜|\bnight\b|今晚|明晚|昨晚|昨夜", line, re.I))
        offset = self.offset
        zone = re.search(r"UTC\s*([+-]\s*\d{1,2}(?:\.\d+)?)?", line, re.I)
        if zone:
            offset = timedelta(hours=float(zone[1].replace(" ", ""))) if zone[1] else timedelta(0)
        elif "东京" in line or "Tokyo" in line:
            offset = timedelta(hours=9)
        elif "工程钟" in line:
            offset = timedelta(hours=-11)
        result = []
        for m in _CLOCK.finditer(line):
            h = _number(m[1]); minute = int(m[2]) if m[2] else 30 if m[4] == "半" else _number(m[3])
            if h > 23 or minute > 59:
                return []
            t = day + timedelta(days=int(night and h < 12), hours=h, minutes=minute) - offset
            result.append((m.start(), m.end(), t))
        return result

    def _fault_text(self, raw, issued):
        """Fault-only improvements; keep accepted terrain/flat decoding unchanged."""
        line = normalize(raw).translate(_TRAD)
        # The shared offline decoder's Latin alphabet omits '+', splitting UTC+9.
        for match in reversed(list(re.finditer(r"[A-Za-z][A-Za-z0-9 +,.:;'()/\-]{15,}", line))):
            segment = match.group()
            if len(re.findall(r"[A-Za-z]{2,}", segment)) < 4:
                continue
            scores = [(_en_score(_shift(segment, k)), k) for k in range(26)]
            score, shift = max(scores)
            if shift and score >= 3 and score > scores[0][0] + 1:
                line = line[:match.start()] + _shift(segment, shift) + line[match.end():]
        for span, text in decode_solfege(line):
            line = line.replace(span, text)
        for span, text in decode_morse(line):
            line = line.replace(span, text)
        line = re.sub(r"\([^A-Za-z0-9\u4e00-\u9fff]*\)", "", line)
        line = re.sub(r"\((?:顺便|车停|第\s*\d|有事|工号)[^)]*\)", "", line)
        line = re.sub(r"([零〇一二两三四五六七八九十]+|\d+)[点时]([一三])刻", lambda m: f" {_number(m[1])}:{15 if m[2] == '一' else 45:02d} ", line)
        line = re.sub(r"(\d{1,2}/\d{1,2})(?=[零〇一二两三四五六七八九十])", r"\1 ", line)
        return line

    def _fault_store(self, onset, line, raw, issued, supersedes=()):
        if onset in self.superseded_faults:
            return
        for old in supersedes:
            if old != onset:
                self.superseded_faults.add(old)
                self.events.pop(('fault', old), None)
                old_key, new_key = old.isoformat(), onset.isoformat()
                self.fault_aliases[old_key] = new_key
                if old_key in self.fault_attempts:
                    count, retry_at = self.fault_attempts.pop(old_key)
                    current_count, current_retry = self.fault_attempts.get(new_key, (0, retry_at))
                    self.fault_attempts[new_key] = (min(2, count + current_count), max(retry_at, current_retry))
        effect = 'I' if re.search(r"全废|废片|几乎归零|近乎为零|garbage|useless|frames.*lost|データ.*使え", line, re.I) else 'II' if re.search(r"效率.*(?:下降|降低|往下)|吞吐量.*(?:掉|只剩)|efficien", line, re.I) else '?'
        key = ('fault', onset)
        old = self.events.get(key)
        if old and effect == '?':
            effect = old['effect']
        confidence = .9 if re.search(r"工程|通知|report|报修|報告", line, re.I) else .75
        sources = list(old.get('sources', [old['source']])) if old else []
        if raw not in sources:
            sources.append(raw)
        self.events[key] = {'kind': 'fault', 'start': onset, 'effect': effect,
                            'subject': 'guider', 'issued': min(issued, old['issued']) if old else issued,
                            'source': raw, 'sources': sources,
                            'confidence': max(confidence, old.get('confidence', 0)) if old else confidence,
                            'policy': 'at_onset' if onset >= (min(issued, old['issued']) if old else issued) else 'data_confirm'}

    def _fault_line(self, raw, issued):
        line = self._fault_text(raw, issued)
        if re.search(r"下雨了.*顺延一天", line):
            dates = list(_DATE.finditer(line))
            if len(dates) == 1:
                date = (int(dates[0][1]), int(dates[0][2]))
                candidates = self.conditional_faults.get(date, [])
                if len(candidates) == 1:
                    old = candidates[0]
                    self._fault_store(old + timedelta(days=1), line, raw, issued, [old])
                    self.conditional_faults.pop(date, None)
                    return True
            return False
        retrospective = bool(re.search(r"吞吐量.*(?:掉|下降|降到)|计数.*(?:掉|跌)|单独.*(?:跳|掉|下)|下降.*没恢复", line))
        if not re.search(r"导星相机|ガイ[ドダ]ー?カメラ|guider|吞吐量.*(?:掉|只剩)|效率.*下降", line, re.I) and not retrospective:
            return None
        if _BAD.search(line) or re.search(r"对吗|对吧|是不是|难道|我记得|没错吧|好像|是.*吗|是.*吧|会不会", line):
            return False
        conditional = bool(re.search(r"若|要是|倘若|如果", line) and '顺延' in line)
        if conditional:
            main = re.split(r"[;。]|若|要是|倘若|如果", line, maxsplit=1)[0]
            times = self._times(main, issued)
            if len(times) != 1:
                return False
            t = times[0][2]
            date = (t + self.offset).month, (t + self.offset).day
            pending = self.conditional_faults.setdefault(date, [])
            if t not in pending:
                pending.append(t)
            # Conditional schedules have two possible onsets until confirmed publicly.
            return False
        if re.search(r"第一段.*平场.*(?:结束|完了)|test window (?:no\.?\s*)?1 ends", line, re.I):
            dates = list(_DATE.finditer(line))
            if len(dates) != 1:
                return False
            d = dates[0]
            anchor = self._times(f'{d[1]}/{d[2]} 12:00', issued)
            if not anchor:
                return False
            noon = anchor[0][2]
            windows = sorted((e['start'], e['end']) for e in self.events.values()
                             if e['kind'] == 'flat' and noon <= e['start'] < noon + timedelta(days=1))
            duration = self._fault_duration(line)
            if windows and duration is not None:
                self._fault_store(windows[0][1] + duration, line, raw, issued)
                return True
            return False
        if '比上面' in line and '按钟点' in line:
            dates = list(_DATE.finditer(line))
            duration = self._fault_duration(line)
            if len(dates) != 2 or duration is None:
                return False
            target = self._times(f'{dates[0][1]}/{dates[0][2]} 12:00', issued)
            refs = [e['start'] for e in self.events.values() if e['kind'] == 'fault'
                    and ((e['start'] + self.offset).month, (e['start'] + self.offset).day) == (int(dates[1][1]), int(dates[1][2]))]
            if len(refs) != 1 or not target:
                return False
            clock = refs[0] + self.offset
            t = target[0][2] + self.offset
            t = t.replace(hour=clock.hour, minute=clock.minute) - self.offset
            self._fault_store(t + (-duration if '早' in line else duration), line, raw, issued)
            return True
        times = self._times(line, issued)
        if not times and retrospective and not _DATE.search(line) and not re.search(r"出头|点多|時多", line):
            # Retrospective clock-only statements refer to the most recent occurrence;
            # keep them data-confirm-only, never use them for an onset timer.
            times = self._times('刚才 ' + line, issued)
            times = [(a, b, t - timedelta(days=1) if t > issued else t) for a, b, t in times]
        if re.search(r"取消|cancelled|canceled|中止", line, re.I):
            for _, _, t in times:
                self.superseded_faults.add(t)
                self.events.pop(('fault', t), None)
            return bool(times)
        if re.search(r"不对|记错|搞错|更正", line):
            if not times and len(list(_DATE.finditer(line))) > 1:
                # A cross-midnight correction can explicitly give two different dates.
                # Bind each clock to its own preceding date, never to the other clause.
                dates = list(_DATE.finditer(line))
                for clock in _CLOCK.finditer(line):
                    preceding = [d for d in dates if d.end() <= clock.start()]
                    if preceding:
                        sub = self._times(line[preceding[-1].start():clock.end()], issued)
                        if len(sub) == 1:
                            times.append((clock.start(), clock.end(), sub[0][2]))
            if len(times) != 2 or not re.search(r"不对.*(?:是|定|改)|更正.*为", line):
                return False
            self._fault_store(times[-1][2], line, raw, issued, [times[0][2]])
            return True
        if re.search(r"推迟|延期|postpon", line, re.I):
            duration = self._fault_duration(line)
            if len(times) == 1 and duration is not None:
                self._fault_store(times[0][2] + duration, line, raw, issued, [times[0][2]])
                return True
            return False
        if re.search(r"同一|之后再|后再|提前|早于|出头|多开始", line):
            # A reference with no unique anchor is never a report trigger.
            if not re.search(r"同一件事|同一.*UTC", line, re.I):
                return False
        if len(times) != 1:
            return False
        self._fault_store(times[0][2], line, raw, issued)
        return True

    @staticmethod
    def _fault_duration(line):
        text = line.lower().replace('小時', '小时')
        for pattern, minutes in ((r'一个半小时|an hour and a half|one and a half hours', 90),
                                 (r'半小时|half an hour|half hour', 30)):
            if re.search(pattern, text):
                return timedelta(minutes=minutes)
        h = re.search(rf'({_NUM})\s*(?:个)?小时', text)
        m = re.search(rf'({_NUM})\s*(?:分钟|分)', text)
        english = re.search(r'(\d+)\s*minutes', text)
        eh = re.search(r'(one|two|an|\d+)\s*hours?', text)
        if h or m or english or eh:
            minutes = 60 * _number(h[1]) if h else 0
            if eh and not h:
                minutes += 60 * ({'one': 1, 'an': 1, 'two': 2}.get(eh[1], int(eh[1]) if eh[1].isdigit() else 0))
            minutes += _number(m[1]) if m else int(english[1]) if english else 0
            return timedelta(minutes=minutes)
        return None

    def ingest(self, messages):
        before = dict(self.terrain)
        changed = False
        for message in messages:
            reason = message.get("reason") or message.get("text") or ""
            if not reason or not message.get("issued_at_utc"):
                continue
            key = (message.get("request_id"), message["issued_at_utc"], reason)
            if key in self.seen:
                continue
            self.seen.add(key)
            changed = True
            issued = _utc(message["issued_at_utc"])
            deferred = []
            for number, raw in enumerate(reason.splitlines(), 1):
                line = _decoded(raw, (issued+self.offset).day)
                self._terrain(line)
                fault_status = self._fault_line(raw, issued)
                if fault_status is False:
                    self.unresolved.append((message.get("request_id"), number, raw))
                    if re.search(r"第一段|比上面|test window", self._fault_text(raw, issued), re.I):
                        deferred.append((number, raw))
                kind = "flat" if _FLAT.search(line) else "fault" if _FAULT.search(line) else None
                if kind == 'fault':
                    continue  # handled above with correction-aware fault-only decoding
                if kind is None:
                    continue
                if _BAD.search(line):
                    continue
                if re.search(r"对吗|对吧|是不是|难道|没错吧|会不会|[?？]", line):
                    self.unresolved.append((message.get("request_id"), number, raw))
                    continue
                times = self._times(line, issued)
                cancelled = bool(re.search(r"取消|cancelled|canceled|中止", line, re.I))
                if cancelled:
                    starts = [a[2] for a, b in zip(times, times[1:])
                              if re.fullmatch(r"\s*(?:到|至|[-–—~〜～]|to)\s*", line[a[1]:b[0]], re.I)]
                    if not starts:
                        starts = [t for _, _, t in times]
                    if kind == 'flat':
                        self.cancelled_flat_starts.update(starts)
                    for k, event in list(self.events.items()):
                        if event["kind"] == kind and event["start"] in starts:
                            del self.events[k]
                    continue
                if not times or (kind == "fault" and len(times) != 1):
                    self.unresolved.append((message.get("request_id"), number, raw))
                    continue
                if kind == "flat":
                    windows = []
                    for a, b in zip(times, times[1:]):
                        if not re.fullmatch(r"\s*(?:到|至|[-–—~〜～]|to)\s*", line[a[1]:b[0]], re.I):
                            continue
                        start, end = a[2], b[2]
                        if end <= start:
                            end += timedelta(days=1)
                        if end - start > timedelta(hours=1):
                            continue
                        windows.append((start, end))
                    correction = bool(re.search(r"不对|记错|搞错|更正|推迟|延期", line))
                    if correction:
                        if len(windows) != 2 or not re.search(r"更正.*为|不对.*(?:是|改)", line):
                            self.unresolved.append((message.get("request_id"), number, raw))
                            continue
                        old, new = windows
                        if old != new:
                            self.superseded_flat_windows.add(old)
                            self.events.pop((kind, *old), None)
                        windows = [new]
                    for start, end in windows:
                        if start in self.cancelled_flat_starts or (start, end) in self.superseded_flat_windows:
                            continue
                        self.events[(kind, start, end)] = {"kind": kind, "start": start, "end": end, "issued": issued}
                else:
                    if re.search(r"不对|记错|更正|推迟|延期|同一|之后再|后再|提前|早于", line):
                        self.unresolved.append((message.get("request_id"), number, raw))
                        continue
                    t = times[0][2]
                    effect = "I" if re.search(r"全废|废片|几乎归零|frames.*lost", line, re.I) else "II" if re.search(r"效率.*下降|吞吐量.*(?:掉|只剩)", line) else "?"
                    self.events[(kind, t)] = {"kind": kind, "start": t, "effect": effect, "subject": "guider" if re.search(r"导星|guider|ガイド", line, re.I) else "unknown", "issued": issued, "source": raw}
            # All lines in a public message arrive together: resolve forward references
            # only after their flat windows have been parsed, never from future messages.
            for number, raw in deferred:
                if self._fault_line(raw, issued):
                    self.unresolved.remove((message.get('request_id'), number, raw))
        if not changed:
            return self.version
        windows = sorted((e["start"], e["end"]) for e in self.events.values() if e["kind"] == "flat")
        merged = []
        for a, b in windows:
            if merged and a <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(b, merged[-1][1]))
            else:
                merged.append((a, b))
        self.flat_windows = merged
        self.flat_starts = [a for a, _ in merged]
        if before != self.terrain:
            self.version += 1
        return self.version
