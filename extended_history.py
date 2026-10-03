"""500 team's public fixture selector. Preserve source semantics, never infer 90-minute scope."""
import json
import re
from datetime import date
from adapters import decode
from dom import Tree


def history_url(tid):
    return f'https://liansai.500.com/index.php?c=teams&a=ajax_fixture&records=100&tid={tid}&hoa=0'


def parse_history(body, tid, url, at):
    data=json.loads(decode(body))
    if not isinstance(data,dict) or str(data.get('tid'))!=tid or url!=history_url(tid):
        raise ValueError('HISTORY_TEAM_IDENTITY_MISMATCH')
    if not isinstance(data.get('list'),list) or len(data['list'])>100:
        raise ValueError('HISTORY_SCHEMA_CHANGED')
    rows=[];seen={};rejected=[]
    for raw in data['list']:
        try:
            if not isinstance(raw,dict):raise ValueError('ROW_SCHEMA')
            def ident(key):
                value=str(raw.get(key,''))
                if not re.fullmatch(r'[1-9]\d*',value):raise ValueError('INVALID_'+key)
                return value
            home,away=ident('HOMETEAMID'),ident('AWAYTEAMID')
            if (home==tid)+(away==tid)!=1:raise ValueError('ROW_TEAM_IDENTITY')
            mid=ident('FIXTUREID')
            day=date.fromisoformat(raw['MATCHDATE']).isoformat()
            score=[]
            for key in ('HOMESCORE','AWAYSCORE'):
                value=raw.get(key)
                if type(value)!=int or value<0:raise ValueError('UNSETTLED_SCORE')
                score.append(value)
            if raw.get('STATUSID')!=5:raise ValueError('NOT_FINISHED')
            half=[raw.get('HOMEHTSCORE'),raw.get('AWAYHTSCORE')]
            half=half if all(type(x)==int and x>=0 for x in half) else None
            if not all(isinstance(raw.get(k),str) and raw[k].strip() for k in ('HOMETEAMSXNAME','AWAYTEAMSXNAME','SIMPLEGBNAME')):raise ValueError('MISSING_NAMES')
            item=dict(source_match_id=mid,date=day,date_precision='DAY',league=raw['SIMPLEGBNAME'],
                league_id=str(raw.get('MATCHID','')),season_id=str(raw.get('SEASONID','')),
                home=dict(id=home,name=raw['HOMETEAMSXNAME']),away=dict(id=away,name=raw['AWAYTEAMSXNAME']),
                displayed_score=':'.join(map(str,score))+(' ('+':'.join(map(str,half))+')' if half else ''),
                fulltime_90=None,score_scope='SOURCE_DISPLAY_ONLY',
                displayed_team_outcome=Tree(raw.get('RESULT','')).root.text(),
                venue_role='HOME' if home==tid else 'AWAY',neutral_venue=None,
                source_url=url,collected_at=at,
                historical_market_observation=dict(
                    scope='SOURCE_FIXTURE_ROW_UNDATED_NOT_ODDS_HISTORY',quoted_at=None,
                    european=dict(home=raw.get('WIN'),draw=raw.get('DRAW'),away=raw.get('LOST'),provider='PAGE_DEFAULT_AVERAGE'),
                    asian=dict(line=raw.get('HANDICAPLINE'),line_text=raw.get('HANDICAPLINENAME'),home=raw.get('HOMEMONEYLINE'),away=raw.get('AWAYMONEYLINE'),provider='PAGE_DEFAULT_UNVERIFIED'),
                    totals=dict(line_text=raw.get('HANDINAME'),over=raw.get('BIGMONEYLINE'),under=raw.get('SMALLMONEYLINE'),provider='PAGE_DEFAULT_UNVERIFIED')))
            if mid in seen:
                if item!=seen[mid]:raise ValueError('CONFLICTING_DUPLICATE_MATCH')
                continue
            seen[mid]=item;rows.append(item)
        except (ValueError,KeyError,TypeError) as exc:
            if str(exc) in ('ROW_TEAM_IDENTITY','CONFLICTING_DUPLICATE_MATCH'):raise
            rejected.append(dict(reason=str(exc),source_match_id=str(raw.get('FIXTUREID','')) if isinstance(raw,dict) else None))
    if data['list'] and not rows:raise ValueError('NO_VALID_HISTORY_ROWS')
    return dict(records=sorted(rows,key=lambda r:(r['date'],r['source_match_id']),reverse=True),
        source_url=url,collected_at=at,rejected_rows=rejected,requested_limit=100,
        returned_count=len(data['list']),coverage='LAST_100_SOURCE_RECORDS_NOT_FULL_HISTORY',
        filters=dict(venue='ALL_LISTED_HOME_AWAY',competition='ALL',neutral_venue_verified=False))
