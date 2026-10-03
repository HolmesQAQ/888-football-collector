"""Historical 500 result evidence, separate from sales status and odds."""
import re
from dom import Tree, Node
from adapters import decode
from model import OUTCOMES


def score(text):
    found = re.fullmatch(r'\s*(\d+)\s*[-:]\s*(\d+)\s*', text)
    return [int(x) for x in found.groups()] if found else None


def outcome(pair):
    return '胜' if pair[0] > pair[1] else '负' if pair[0] < pair[1] else '平'


def empty_result(source, ident, url, at):
    return dict(status='UNKNOWN',status_text='未取得',halftime=None,fulltime_90=None,
        displayed_score=None,extra_time_note=None,source=source,source_url=url,
        source_match_id=ident,collected_at=at,verification='SINGLE_SOURCE_OBSERVED',
        actual_events={},halftime_outcome=None,gaps=[],evidence_urls=[url])


def okooo_result_main(row, match, url, at):
    result=empty_result('okooo',match['source_match_id'],url,at)
    nodes=[n for box in row.cls('more_bg') for n in box.cls('p1')]
    result['displayed_score']=score(nodes[0].text()) if len(nodes)==1 else None
    match['result']=result


def okooo_result_more(root, match, url, at):
    r=match.setdefault('result',empty_result('okooo',match['source_match_id'],url,at))
    r['evidence_urls']=list(dict.fromkeys(r['evidence_urls']+[url]))
    selected={}
    for n in root.cls('saiguo_color'):
        play={'2':'BF','3':'BQC','4':'JQS'}.get(n.attrs.get('data-wf'))
        labels=n.cls('peilv')
        if not play or not labels:continue
        label=labels[0].text().replace(' ','').replace('其它','其他')
        if play=='BF':label=label.replace('-',':')
        if play=='JQS':label='7+' if label in ('总>6球','7+','7球以上') else label.replace('总','').replace('球','')
        if label in OUTCOMES[play]:selected.setdefault(play,set()).add(label)
    # Require unambiguous settlement markers, not merely a closed sales flag or live score.
    if any(len(values)!=1 for values in selected.values()):
        r.update(status='CONFLICT',status_text='赛果冲突',gaps=['结算标记不唯一']);return
    events={p:next(iter(v)) for p,v in selected.items()}
    if not all(p in events for p in ('BF','JQS','BQC')):
        r['gaps']=['未取得完整结算标记，不能确认完赛'];return
    full=score(events['BF']) or r['displayed_score']
    if full is not None:
        bf=':'.join(map(str,full))
        expected_bf=bf if bf in OUTCOMES['BF'] else outcome(full)+'其他'
        if (events['BF']!=expected_bf or events['JQS']!=(str(sum(full)) if sum(full)<7 else '7+')
            or events['BQC'].split('/')[1]!=outcome(full)
            or (r['displayed_score'] is not None and full!=r['displayed_score'])):
            r.update(status='CONFLICT',status_text='赛果冲突',gaps=['比分与结算标记不一致']);return
        events['SPF']=outcome(full)
        if match.get('handicap') is not None:events['RQSPF']=outcome([full[0]+int(match['handicap']),full[1]])
    r.update(status='FINISHED',status_text='完',fulltime_90=full,actual_events=events,
        halftime_outcome=events['BQC'].split('/')[0],source_url=url,collected_at=at,
        gaps=['澳客竞彩页提供半场胜平负，未提供半场精确比分']+([] if full is not None else ['未取得精确全场比分']))


def attach_results(body, matches, target_date, url, at):
    root = Tree(decode(body)).root
    selects = root.all(id='sel_expect')
    options = [n for n in selects[0].all() if n.tag == 'option'] if selects else []
    selected = next((n for n in options if 'selected' in n.attrs), options[0] if len(options) == 1 else None)
    if selected is None or selected.attrs.get('value') != target_date:
        raise ValueError('比分页销售日不匹配')
    rows = {n.attrs['fid']: n for n in root.all(fid=None, order=None, gy=None)}
    count = 0
    for m in matches:
        row = rows.get(m['source_match_id'])
        if row is None:
            continue
        cells = [n for n in row.children if isinstance(n, Node) and n.tag == 'td']
        if len(cells) < 9:
            continue
        label = cells[4].text().strip()
        status = {'完':'FINISHED','完场':'FINISHED','推迟':'POSTPONED','延期':'POSTPONED',
                  '取消':'CANCELLED','中断':'SUSPENDED','腰斩':'ABANDONED','未':'PENDING'}.get(label, 'UNKNOWN')
        extra = ' '.join(n.text() for n in root.all(parentid=row.attrs.get('id', '')))
        explicit = re.search(r'90分钟\s*\[\s*(\d+)\s*[-:]\s*(\d+)\s*\]', extra)
        full = [int(x) for x in explicit.groups()] if explicit else score(cells[6].text())
        half = score(cells[8].text())
        # An extra-time/penalty annotation without explicit 90-minute evidence is ambiguous.
        if not explicit and any(x in extra + label for x in ('120分钟','点球','加时')):
            full = None
        result = dict(status=status, status_text=label, halftime=half,
            fulltime_90=full if status == 'FINISHED' else None, displayed_score=score(cells[6].text()),
            extra_time_note=extra or None, source='500', source_url=url,
            source_match_id=m['source_match_id'], collected_at=at,
            verification='SINGLE_SOURCE_OBSERVED', actual_events={},halftime_outcome=outcome(half) if half is not None else None,
            gaps=[] if half is not None else ['未取得半场精确比分'],evidence_urls=[url])
        if status == 'FINISHED' and full is not None:
            total = sum(full)
            bf = ':'.join(map(str,full))
            events = dict(SPF=outcome(full), JQS=str(total) if total < 7 else '7+',
                          BF=bf if bf in OUTCOMES['BF'] else outcome(full)+'其他')
            if m.get('handicap') is not None:
                events['RQSPF'] = outcome([full[0]+int(m['handicap']), full[1]])
            if half is not None:
                events['BQC'] = outcome(half)+'/'+outcome(full)
            result['actual_events'] = events
        m['result'] = result
        count += 1
    return count
