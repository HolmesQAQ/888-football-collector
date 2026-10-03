"""Bounded, source-observed team evidence. No predictions or historical rank inference."""
import re
from calendar import monthrange
from datetime import date, timedelta
from dom import Tree, Node
from adapters import decode
from model import now
from extended_history import history_url,parse_history


def cells(row):
    return [n for n in row.children if isinstance(n, Node) and n.tag in ('td', 'th')]


def team(cell):
    found=[]
    for a in cell.all(href=None):
        hit=re.fullmatch(r'https://liansai\.500\.com/team/(\d+)/', a.attrs['href'])
        if hit: found.append(dict(id=hit[1], name=a.text()))
    return found[0] if len(found)==1 else None


def parse_team(body, team_id, url, at):
    root=Tree(decode(body)).root
    canonical=[n.attrs.get('href') for n in root.all(rel='canonical')]
    if canonical != [url] or url != f'https://liansai.500.com/team/{team_id}/':
        raise ValueError('TEAM_IDENTITY_NOT_CONFIRMED')
    records=[]; rejected=[]; seen={}
    tables=root.cls('lcur_race_list')
    if len(tables)!=1: raise ValueError('RECENT_TABLE_MISSING_OR_AMBIGUOUS')
    rows=[n for n in tables[0].all() if n.tag=='tr']
    if not rows or [c.text() for c in cells(rows[0])][:6] != ['赛事','比赛时间','主队','比分','客队','赛果']:
        raise ValueError('RECENT_HEADERS_CHANGED')
    for row in rows[1:]:
        cs=cells(row)
        try:
            if len(cs)<6: raise ValueError('COLUMN_COUNT')
            day=date.fromisoformat(cs[1].text()).isoformat()
            home,away=team(cs[2]),team(cs[4])
            if not home or not away or (home['id']==team_id)+(away['id']==team_id)!=1:
                raise ValueError('ROW_TEAM_IDENTITY')
            ids=[re.search(r'/fenxi/shuju-(\d+)\.shtml',a.attrs['href']) for a in row.all(href=None)]
            ids=[h[1] for h in ids if h]
            if len(set(ids))!=1: raise ValueError('MATCH_ID_MISSING')
            score=' '.join(cs[3].text().split())
            # Preserve exact source score; its 90-minute scope is not established by this table.
            if not re.fullmatch(r'\d+\s*:\s*\d+(?:\s*\(\d+\s*:\s*\d+\))?',score):
                raise ValueError('UNSETTLED_OR_AMBIGUOUS_SCORE')
            item=dict(source_match_id=ids[0],date=day,date_precision='DAY',league=cs[0].text(),
                      home=home,away=away,displayed_score=score,fulltime_90=None,
                      score_scope='SOURCE_DISPLAY_ONLY',displayed_team_outcome=cs[5].text(),
                      venue_role='HOME' if home['id']==team_id else 'AWAY')
            if ids[0] in seen:
                if seen[ids[0]]!=item: raise ValueError('CONFLICTING_DUPLICATE_MATCH')
                continue
            seen[ids[0]]=item; records.append(item)
        except ValueError as exc:
            if str(exc)=='CONFLICTING_DUPLICATE_MATCH': raise
            rejected.append(dict(reason=str(exc),raw_text=' '.join(row.text().split())))
    standings=[]
    for table in root.cls('llianspm_list_s'):
        trs=[n for n in table.all() if n.tag=='tr']
        if not trs or [c.text() for c in cells(trs[0])] != ['排名','队伍','赛','胜','平','负','积分']:
            rejected.append(dict(reason='STANDINGS_HEADERS_CHANGED'));continue
        for tr in trs[1:]:
            cs=cells(tr)
            if len(cs)!=7 or not team(cs[1]) or team(cs[1])['id']!=team_id: continue
            try:
                values=[int(cs[i].text()) for i in (0,2,3,4,5,6)]
                rank,played,won,drawn,lost,points=values
                if min(values[:5])<0 or rank<1 or won+drawn+lost!=played: raise ValueError()
                standings.append(dict(rank=rank,played=played,won=won,drawn=drawn,lost=lost,points=points,
                    team=team(cs[1]),as_of=None,season=None,league_id=None,
                    historical_prematch_eligible=False,scope='CURRENT_PAGE_UNDATED'))
            except ValueError: rejected.append(dict(reason='STANDINGS_INVALID_TOTALS'))
    if len(standings)>1: raise ValueError('AMBIGUOUS_STANDINGS')
    upcoming=[]
    for table in root.cls('lweilss_list_s'):
        trs=[n for n in table.all() if n.tag=='tr']
        if not trs or [c.text() for c in cells(trs[0])] != ['比赛时间','对阵','分析']:
            rejected.append(dict(reason='SCHEDULE_HEADERS_CHANGED'));continue
        for tr in trs[1:]:
            try:
                cs=cells(tr)
                if len(cs)!=3:raise ValueError('SCHEDULE_COLUMNS')
                day=date.fromisoformat(cs[0].text()).isoformat()
                links=cs[1].all(href=None)
                teams=[]
                for a in links:
                    h=re.fullmatch(r'https://liansai\.500\.com/team/(\d+)/',a.attrs['href'])
                    if h:teams.append(dict(id=h[1],name=a.text()))
                if len(teams)!=2 or sum(t['id']==team_id for t in teams)!=1:raise ValueError('SCHEDULE_TEAM_IDENTITY')
                mids=[re.search(r'/fenxi/shuju-(\d+)\.shtml',a.attrs['href']) for a in cs[2].all(href=None)]
                mids=[h[1] for h in mids if h]
                if len(set(mids))!=1:raise ValueError('SCHEDULE_MATCH_ID')
                upcoming.append(dict(source_match_id=mids[0],date=day,date_precision='DAY',home=teams[0],away=teams[1],
                    source_url=url,collected_at=at,neutral_venue=None,scope='CURRENT_SCHEDULE_OBSERVATION',prematch_availability_proven=False))
            except (ValueError,IndexError) as exc:rejected.append(dict(reason=str(exc)))
    return dict(source='500',team_id=team_id,source_url=url,collected_at=at,source_updated_at=None,
                records=sorted(records,key=lambda r:(r['date'],r['source_match_id']),reverse=True),
                standings=standings[0] if standings else None,rejected_rows=rejected,
                coverage='VISIBLE_PAGE_WINDOW_ONLY',independently_verified=False,upcoming_schedule=upcoming)


def for_match(page, kickoff, opponent, match_id):
    # Day-only source cannot prove ordering on match day: exclude the whole day.
    cutoff=date.fromisoformat(kickoff[:10]).isoformat()
    target=date.fromisoformat(cutoff)
    year,month=(target.year-1,12) if target.month==1 else (target.year,target.month-1)
    start=date(year,month,min(target.day,monthrange(year,month)[1])).isoformat()
    prior=[r for r in page['records'] if start<=r['date']<cutoff and r['source_match_id']!=match_id]
    scoped_page=dict(page,records=prior)
    end=(date.fromisoformat(cutoff)+timedelta(days=10)).isoformat()
    future=[r for r in page.get('upcoming_schedule',[]) if cutoff<r['date']<=end and r['source_match_id']!=match_id]
    return dict(**scoped_page,eligible_prior_records=prior,
        history_start_inclusive=start,history_window="PREVIOUS_CALENDAR_MONTH",
        future_10d_observed_schedule=future,
        days_since_last_listed_match=(date.fromisoformat(cutoff)-date.fromisoformat(prior[0]['date'])).days if prior else None,
        interval_scope='CALENDAR_DAYS_FROM_LISTED_RECORD_NOT_VERIFIED_REST_TIME',
        previous_10d_match_ids=[r['source_match_id'] for r in prior if (date.fromisoformat(cutoff)-date.fromisoformat(r['date'])).days<=10],cutoff_exclusive=cutoff,
        excluded_records=len(page['records'])-len(prior),
        recent_3=prior[:3],recent_5=prior[:5],recent_10=prior[:10],
        venue_role_meaning='SOURCE_LISTED_HOME_AWAY_NOT_VERIFIED_PHYSICAL_VENUE',
        home_records=[r for r in prior if r['venue_role']=='HOME'],
        away_records=[r for r in prior if r['venue_role']=='AWAY'],
        h2h_records=[r for r in prior if opponent in (r['home']['id'],r['away']['id'])],
        completeness='PARTIAL_WINDOW_NOT_FULL_HISTORY',
        prematch_availability_proven=False)


def enrich(matches, fetch, imported_sources=(), log=print):
    cache={}
    for m in matches:
        facts=dict(status='UNAVAILABLE',source=m['source'],teams={},gaps=[])
        m['team_evidence']=facts
        if m['source']!='500':
            facts['gaps'].append('OKOOO_TEAM_HISTORY_NOT_IMPLEMENTED');continue
        if m['source'] in imported_sources:
            facts['gaps'].append('LOCAL_IMPORT_NO_TEAM_PAGE');continue
        attrs=m['source_attrs']; home=attrs.get('data-homeid','');away=attrs.get('data-awayid','')
        if not re.fullmatch(r'\d+',home) or not re.fullmatch(r'\d+',away) or home==away:
            facts['gaps'].append('TEAM_IDS_MISSING_OR_INVALID');continue
        for role,tid,opp in [('home',home,away),('away',away,home)]:
            url=f'https://liansai.500.com/team/{tid}/'
            if fetch.stop.is_set(): facts['gaps'].append('STOPPED');break
            if tid not in cache:
                log('读取球队资料：'+m[role+'_team'])
                try:
                    body,at=fetch.get(url);cache[tid]=parse_team(body,tid,url,at)
                    page=cache[tid]
                    page['standings_source_url']=url
                    page['standings_collected_at']=at
                    extended=history_url(tid)
                    try:
                        b,t=fetch.get(extended)
                        history=parse_history(b,tid,extended,t)
                        if not history['records'] and page['records']:raise ValueError('EMPTY_EXPANSION_CONFLICTS_WITH_HOMEPAGE')
                        page.update(history)
                    except Exception as exc:
                        page['history_expansion_error']=str(exc)
                        fetch.attempts.append(dict(url=extended,fetched_at=now(),status='FAILED',error=str(exc)))
                except Exception as exc:
                    cache[tid]=str(exc)
                    fetch.attempts.append(dict(url=url,fetched_at=now(),status='FAILED',error=str(exc)))
            if isinstance(cache[tid],str): facts['gaps'].append(role+':'+cache[tid]);continue
            facts['teams'][role]=for_match(cache[tid],m['kickoff_at'],opp,m['source_match_id'])
        if facts['teams']:
            facts['status']='PARTIAL'
            facts['gaps']+=['仅保留目标比赛日前一个自然月战绩和交锋；不足场数不向前补齐','比分口径未证明为90分钟，不据此计算胜率或净胜球','积分为当前页面未注明日期快照，禁止作为历史赛前排名']
        for dim in ('recent_3_5','home_away_performance','h2h_recent','motivation_rank_phase','schedule_density','future_7_10d_priority'):
            m['coverage_draft'][dim].update(collection_stage='PARTIAL' if facts['teams'] else 'UNAVAILABLE',
                evidence_status=None,reason='见 team_evidence；窗口有限，未独立核验，不代表该维度完整')
