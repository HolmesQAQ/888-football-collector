import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

TZ = timezone(timedelta(hours=8))
PROFILE = 'RULE_PROFILE_888_JCZQ-v2.1'
DIMENSIONS = '''team_coach_news injuries_suspensions expected_lineup official_lineup bench_formation
transfer_registration_availability recent_3_5 longer_trend home_away_performance opponent_quality
h2h_recent tactical_system attack_defense_profile coach_style key_matchups motivation_rank_phase
schedule_density travel_rest future_7_10d_priority weather_pitch jczq_sp asian_market european_market
lineup_release_timing'''.split()
OUTCOMES = {
    'SPF': ['胜', '平', '负'], 'RQSPF': ['胜', '平', '负'],
    'JQS': [str(i) for i in range(7)] + ['7+'],
    'BQC': [a + '/' + b for a in '胜平负' for b in '胜平负'],
    'BF': '1:0 2:0 2:1 3:0 3:1 3:2 4:0 4:1 4:2 5:0 5:1 5:2 胜其他 0:0 1:1 2:2 3:3 平其他 0:1 0:2 1:2 0:3 1:3 2:3 0:4 1:4 2:4 0:5 1:5 2:5 负其他'.split()
}


def now():
    return datetime.now(TZ).isoformat(timespec='seconds')


def digest(obj):
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def price(raw):
    if raw is None:
        return None
    raw = str(raw).strip()
    if not re.fullmatch(r'\d+(?:\.\d+)?', raw):
        return None
    try:
        n = Decimal(raw)
        return str(n.normalize()) if n > 1 and n.is_finite() else None
    except InvalidOperation:
        return None


def timestamp(value):
    if not value:
        return None
    d = datetime.fromisoformat(value)
    return (d.replace(tzinfo=TZ) if d.tzinfo is None else d.astimezone(TZ)).isoformat(timespec='seconds')


def new_match(source, ident, sale_date, match_no, league, home, away, kickoff, handicap, ended, at, url):
    kickoff = timestamp(kickoff)
    sale_status = 'CLOSED' if ended or (kickoff and kickoff <= at) else 'UNKNOWN'
    return dict(source=source, source_match_id=ident, sale_date=sale_date, match_no=match_no,
                league=league, home_team=home, away_team=away, kickoff_at=kickoff,
                handicap=handicap, sale_status=sale_status, source_url=url, collected_at=at,
                quoted_at=None, source_attrs={}, issues=[], markets={p:dict(sale_status=sale_status,
                options={k:dict(value=None, status='MISSING', raw_attribute=None, raw_display=None,
                               source_url=url, collected_at=at, quoted_at=None) for k in keys})
                for p, keys in OUTCOMES.items()})


def set_quote(match, play, option, attr, display, url, at):
    if option not in OUTCOMES.get(play, []):
        match['issues'].append('UNKNOWN_OPTION:' + str(play) + ':' + str(option))
        return
    a, d = price(attr), price(display)
    conflict = a is not None and d is not None and a != d
    value = None if conflict else d or a
    match['markets'][play]['options'][option] = dict(value=value,
        status='CONFLICT' if conflict else 'OBSERVED' if value else 'MISSING',
        raw_attribute=attr, raw_display=display, source_url=url, collected_at=at, quoted_at=None)
    if conflict:
        match['issues'].append('ATTRIBUTE_DISPLAY_CONFLICT:' + play + ':' + option)


def finish_match(match):
    for market in match['markets'].values():
        values = list(market['options'].values())
        count = sum(v['value'] is not None for v in values)
        market['observed_count'] = count
        market['expected_count'] = len(values)
        market['data_status'] = 'CONFLICT' if any(v['status'] == 'CONFLICT' for v in values) else (
            'COMPLETE' if count == len(values) else 'PARTIAL' if count else 'MISSING')
    # Phase-one draft: unattempted dimensions MUST NOT masquerade as valid Coverage statuses.
    match['coverage_draft'] = {k: dict(collection_stage='NOT_ATTEMPTED', evidence_status=None,
        facts=[], source_refs=[], gap_reason='第一阶段尚未采集', expected_available_at=None)
        for k in DIMENSIONS}
    match['coverage_draft']['jczq_sp'] = dict(collection_stage='COLLECTED', evidence_status=None,
        facts=[{'market': p, 'data_status': v['data_status']} for p, v in match['markets'].items()],
        source_refs=[match['source_url']], gap_reason='页面观察值；待跨源、时效和销售状态核验', expected_available_at=None)
    match['coverage_integrity'] = 'INCOMPLETE'
    match['ready_for_analysis'] = False
    return match


def normalized_name(value):
    return re.sub(r'\s+', '', value).casefold()


def compare(matches, aliases=None):
    """Never merge on match number. Aliases require an explicit evidence reference."""
    aliases = aliases or []
    def canonical(name, league):
        for a in aliases:
            if a.get('evidence_url') and a.get('league') == league and name in a.get('names', []):
                return a['canonical']
        return normalized_name(name)
    result = []
    for a in [m for m in matches if m['source'] == '500']:
        candidates = [b for b in matches if b['source'] == 'okooo' and b['sale_date'] == a['sale_date']
                      and b['match_no'][-3:] == a['match_no'][-3:]]
        for b in candidates:
            identity = all(a.get(k) and a[k] == b.get(k) for k in ['league', 'kickoff_at']) and all(
                canonical(a[k], a['league']) == canonical(b[k], b['league']) for k in ['home_team', 'away_team'])
            diffs = []
            if identity:
                for field in ('fulltime_90','halftime','halftime_outcome'):
                    x,y=a.get('result',{}).get(field),b.get('result',{}).get(field)
                    if x is not None and y is not None and x!=y:
                        diffs.append({'field':'result:'+field,'500':x,'okooo':y})
                if a['handicap'] != b['handicap']:
                    diffs.append({'field': 'handicap', '500': a['handicap'], 'okooo': b['handicap']})
                for p, keys in OUTCOMES.items():
                    for k in keys:
                        x, y = a['markets'][p]['options'][k]['value'], b['markets'][p]['options'][k]['value']
                        if x != y:
                            diffs.append({'field': p + ':' + k, '500': x, 'okooo': y})
            result.append(dict(source_500=a['source_match_id'], source_okooo=b['source_match_id'],
                identity_status='MATCHED' if identity and len(candidates) == 1 else 'NEEDS_REVIEW',
                differences=diffs, note='两站值一致不等于独立官方核验；不自动平均或覆盖'))
        if not candidates:
            result.append(dict(source_500=a['source_match_id'],source_okooo=None,
                identity_status='UNMATCHED',differences=[],note='另一来源无对应记录'))
    used={r['source_okooo'] for r in result}
    for b in [m for m in matches if m['source']=='okooo' and m['source_match_id'] not in used]:
        result.append(dict(source_500=None,source_okooo=b['source_match_id'],
            identity_status='UNMATCHED',differences=[],note='另一来源无对应记录'))
    return result
