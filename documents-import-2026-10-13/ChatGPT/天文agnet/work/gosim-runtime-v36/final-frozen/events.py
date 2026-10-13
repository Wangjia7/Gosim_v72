"""Persistent, source-checked operational facts. No source text is executed."""
import math
import re
import unicodedata
from datetime import datetime, timezone, timedelta
from skymath import parse_utc

KINDS={'hardware_work','lamp_test','downtime','weather','terrain'}
DIRECTIONS={'ALL','N','NE','E','SE','S','SW','W','NW'}


def normalize(text):
    return ''.join(c for c in unicodedata.normalize('NFKC',text) if unicodedata.category(c)!='Cf')


def clock_text(text):
    text=normalize(text)
    digits={'零':0,'〇':0,'一':1,'二':2,'两':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9}
    def number(s):
        if s.isdigit():return int(s)
        if '十' in s:
            a,b=s.split('十',1);return (digits.get(a,1) if a else 1)*10+(digits.get(b,0) if b else 0)
        return digits.get(s,0)
    pattern=r'([\d零〇一二两三四五六七八九十]{1,3})(?:点|時|时)(半|整|[\d零〇一二两三四五六七八九十]{1,3}分?)?'
    def replace(m):
        suffix=m[2] or '整';minute=30 if suffix=='半' else 0 if suffix=='整' else number(suffix.rstrip('分'))
        return f'{number(m[1])}:{minute:02d}'
    return re.sub(pattern,replace,text)


def utc_offsets(quote,year):
    text=clock_text(quote);offsets=set()
    for sign,h,m in re.findall(r'UTC\s*([+-])(\d{1,2})(?::(\d{2}))?',text,re.I):
        offsets.add((1 if sign=='+' else -1)*(60*int(h)+int(m or 0)))
    # An explicit same-event local/UTC pair, quoted together, establishes a site
    # conversion. No timezone is guessed from telescope longitude.
    if re.search(r'同一|同じ|same',text,re.I):
        rows=re.findall(r'(\d{1,2})/(\d{1,2})[^\d\n]{0,20}(\d{1,2}):(\d{2})',text)
        if len(rows)==2:
            try:
                local=datetime(year,*map(int,rows[0]),tzinfo=timezone.utc)
                options=[datetime(y,*map(int,rows[1]),tzinfo=timezone.utc) for y in (year-1,year,year+1)]
                utc=min(options,key=lambda t:abs((local-t).total_seconds()))
                offset=int((local-utc).total_seconds()/60)
                if abs(offset)<=14*60:offsets.add(offset)
            except ValueError:pass
    return offsets


def literal_clock(moment,quote):
    text=clock_text(quote)
    clock=bool(re.search(rf'(?<!\d)0?{moment.hour}:0?{moment.minute}(?!\d)',text))
    date=bool(re.search(rf'(?<!\d)0?{moment.month}/0?{moment.day}(?!\d)|{moment.month}月{moment.day}日',text))
    return clock and date


def validate_event(row, sources, survey_start, survey_end):
    if not isinstance(row,dict):return None
    allowed={'event_id','kind','operation','start_utc','end_utc','directions','min_altitude_deg',
             'source_id','quote','time_quote','time_source_id','time_basis','confirmation','replaces','weather_kind',
             'end_quote','local_start','local_end','utc_offset_minutes'}
    if set(row)-allowed or row.get('kind') not in KINDS:return None
    if row.get('operation','upsert') not in {'upsert','cancel'}:return None
    if row.get('confirmation')!='confirmed':return None
    source=sources.get(row.get('source_id'));quote=row.get('quote')
    if not isinstance(source,str) or not isinstance(quote,str) or not quote or quote not in source or len(quote)>1500:return None
    if re.search(r'听说|傳聞|传闻|未确认|没确认|隔壁|別の望遠鏡|rumou?r|unconfirmed',normalize(quote),re.I):return None
    identity=row.get('event_id')
    if not isinstance(identity,str) or not identity or len(identity)>160:return None
    replacement=row.get('replaces')
    if replacement is not None and (not isinstance(replacement,str) or len(replacement)>160):return None
    if row.get('operation')=='cancel':
        if not re.search(r'取消|中止|cancel|不用报|不動|不动',normalize(quote),re.I):return None
        return dict(row)
    try:
        start=parse_utc(row['start_utc']);end=parse_utc(row['end_utc']) if row.get('end_utc') else start
    except (KeyError,ValueError,TypeError,AttributeError):return None
    if start.tzinfo is None or end.tzinfo is None:return None
    if not survey_start-7*86400<=start.timestamp()<=survey_end+7*86400 or end<start or end.timestamp()>survey_end+7*86400:return None
    if row['kind'] in {'lamp_test','downtime','weather'} and end<=start:return None
    if row['kind']!='terrain':
        time_quote=row.get('time_quote',quote)
        time_source=sources.get(row.get('time_source_id',row.get('source_id')),source)
        if not isinstance(time_quote,str) or not time_quote or not isinstance(time_source,str) or time_quote not in time_source:return None
        # Conversion must cite a UTC anchor from the supplied text. Unknown local
        # timezone and an encoded time without its anchor remain unresolved.
        if row.get('time_basis') not in {'explicit_utc','cross_reference'} or 'UTC' not in normalize(time_quote).upper():return None
        if row['time_basis']=='explicit_utc':
            text=normalize(time_quote)
            times=re.findall(r'(\d{1,2})/(\d{1,2})[^\d\n]{0,20}(\d{1,2}):(\d{2})',text)
            if not times or (start.month,start.day,start.hour,start.minute) not in [tuple(map(int,v)) for v in times]:return None
        else:
            offset=row.get('utc_offset_minutes')
            if type(offset) is not int or utc_offsets(time_quote,start.year)!={offset}:return None
            try:local=datetime.fromisoformat(row['local_start']).replace(tzinfo=timezone.utc)
            except (KeyError,ValueError,TypeError):return None
            if abs((local-timedelta(minutes=offset)-start).total_seconds())>.5 or not literal_clock(local,quote):return None
        if row['kind'] in {'lamp_test','downtime','weather'}:
            end_quote=row.get('end_quote',quote)
            if not isinstance(end_quote,str) or not end_quote or end_quote not in source:return None
            if row['time_basis']=='explicit_utc':
                if 'UTC' not in normalize(end_quote).upper():return None
                # A start date also anchors an interval crossing midnight.
                text=clock_text(end_quote)
                if not re.search(rf'(?<!\d)0?{end.hour}:0?{end.minute}(?!\d)',text):return None
                dated=re.findall(r'(\d{1,2})/(\d{1,2})[^\d\n]{0,20}(\d{1,2}):(\d{2})',text)
                exact=(end.month,end.day,end.hour,end.minute) in [tuple(map(int,v)) for v in dated]
                if not exact and (end-start>timedelta(hours=24) or not literal_clock(start,end_quote)):return None
            else:
                try:local_end=datetime.fromisoformat(row['local_end']).replace(tzinfo=timezone.utc)
                except (KeyError,ValueError,TypeError):return None
                if abs((local_end-timedelta(minutes=offset)-end).total_seconds())>.5:return None
                if not literal_clock(local_end,end_quote) and not literal_clock(local,end_quote):return None
    directions=row.get('directions',['ALL'])
    if not isinstance(directions,list) or not directions or any(d not in DIRECTIONS for d in directions):return None
    if row['kind']=='terrain':
        h=row.get('min_altitude_deg')
        if type(h) not in (int,float) or not math.isfinite(h) or not 0<=h<=90:return None
    if row['kind']=='weather' and row.get('weather_kind') not in {'rain','storm','overcast','haze','cold_snap'}:return None
    return {**row,'start':start.timestamp(),'end':end.timestamp(),'directions':directions}


class EventQueue:
    def __init__(self, planner):
        self.p=planner;self.events={};self.cancelled=set();self.revision=0
        self.accepted=0;self.rejected=0;self.last_report_event=None
        self.start=planner.nights[0][0].timestamp();self.end=planner.survey_end.timestamp()

    def apply(self, rows, sources):
        # Apply upserts before cancellations, including a cancellation delivered
        # earlier than the segment containing its original event.
        ordered=sorted(rows,key=lambda r:r.get('operation')=='cancel' if isinstance(r,dict) else False)
        for row in ordered:
            event=validate_event(row,sources,self.start,self.end)
            if event is None:self.rejected+=1;continue
            identity=event['event_id']
            if event.get('operation')=='cancel':
                identity=event.get('replaces') or identity
                self.cancelled.add(identity)
                if identity in self.events:self.events[identity]['cancelled']=True
                self.revision+=1;self.accepted+=1;continue
            if event.get('replaces'):
                old=event['replaces'];self.cancelled.add(old)
                if old in self.events:self.events[old]['cancelled']=True
            event['cancelled']=identity in self.cancelled
            old=self.events.get(identity)
            if old and all(old.get(k)==v for k,v in event.items()):continue
            if old:event['processed']=old.get('processed',False) and old.get('start')==event['start'] and old.get('kind')==event['kind']
            self.events[identity]=event;self.revision+=1;self.accepted+=1

    def active(self,stamp):
        return [e for e in self.events.values() if not e.get('cancelled') and
                e['kind']!='terrain' and e['start']<=stamp<e['end']]

    def blocked_intervals(self,start,end):
        return [(max(start,e['start']),min(end,e['end'])) for e in self.events.values()
                if not e.get('cancelled') and (e['kind'] in {'lamp_test','downtime'} or
                   (e['kind']=='weather' and e.get('weather_kind') in {'rain','storm'} and 'ALL' in e['directions']))
                and e['start']<end and e['end']>start]

    def unavailable_until(self,stamp):
        ends=[e['end'] for e in self.active(stamp) if e['kind'] in {'lamp_test','downtime'} or
              (e['kind']=='weather' and e.get('weather_kind') in {'rain','storm'} and 'ALL' in e['directions'])]
        return max(ends) if ends else None

    def next_boundary(self,stamp,end):
        return min([end]+[e['start'] for e in self.events.values() if not e.get('cancelled') and
                    e['kind'] in {'hardware_work','lamp_test','downtime','weather'} and stamp<e['start']<end])

    def due_hardware(self,stamp):
        due=[e for e in self.events.values() if not e.get('cancelled') and not e.get('processed') and
             e['kind']=='hardware_work' and e['start']<=stamp]
        return min(due,key=lambda e:(e['start'],e['event_id'])) if due else None

    def reported(self,event):
        self.last_report_event=event['event_id'];event['processed']=True

    def report_result(self,result):
        if result.get('correct') and result.get('repaired'):
            # One repair resolves all earlier overlapping notifications.
            current=self.events.get(self.last_report_event)
            if current:
                for e in self.events.values():
                    if e['kind']=='hardware_work' and e['start']<=current['start']:e['processed']=True
        self.last_report_event=None

    def terrain_limit(self,az):
        positions={'N':0,'NE':45,'E':90,'SE':135,'S':180,'SW':225,'W':270,'NW':315}
        limits=[]
        for e in self.events.values():
            if e.get('cancelled') or e['kind']!='terrain':continue
            if any(d=='ALL' or abs((az-positions[d]+180)%360-180)<=22.5 for d in e['directions']):
                limits.append(e['min_altitude_deg'])
        return max(limits) if limits else None

    def summary(self):
        return {'revision':self.revision,'accepted':self.accepted,'rejected':self.rejected,
                'pending_hardware':sum(e['kind']=='hardware_work' and not e.get('processed') and not e.get('cancelled') for e in self.events.values()),
                'events':len(self.events),'cancelled':len(self.cancelled)}
