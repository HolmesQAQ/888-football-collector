"""Source-specific mappings established from archived source HTML."""
import re
import json
from datetime import date
from dom import Tree, Node
from model import new_match, set_quote, finish_match, timestamp


def parse_500_live(body, target_date, url, at):
    """Public score page: explicit sp/rqsp are JC odds; numeric company keys are not."""
    source = decode(body)
    root = Tree(source).root
    selectors = root.all(id='sel_expect')
    options = [n for n in selectors[0].all() if n.tag == 'option'] if selectors else []
    selected = next((n for n in options if 'selected' in n.attrs), options[0] if len(options)==1 else None)
    actual_date = selected.attrs.get('value') if selected else None
    if actual_date != target_date:
        return [], dict(status='DATE_MISMATCH', observed_date=actual_date, adapter='500_PUBLIC_SCORE')
    found = re.search(r'var\s+liveOddsList\s*=\s*(\{.*?\})\s*;', source, re.S)
    odds = json.loads(found.group(1)) if found else {}
    matches = []
    for row in root.all(fid=None, order=None, gy=None):
        a = row.attrs
        cells = [n for n in row.children if isinstance(n, Node) and n.tag=='td']
        names = a['gy'].split(',')
        if len(cells)<8 or len(names)!=3:
            raise ValueError('500比分页身份结构变化，停止解析')
        day_time = re.fullmatch(r'(\d{2}-\d{2})\s+(\d{2}:\d{2})', cells[3].text())
        if not day_time:
            raise ValueError('500比分页开赛时间不可核验')
        sale = date.fromisoformat(target_date)
        candidates = []
        for year in (sale.year-1,sale.year,sale.year+1):
            try: candidates.append(date.fromisoformat(str(year)+'-'+day_time.group(1)))
            except ValueError: pass
        kickoff_day = min(candidates, key=lambda d:abs((d-sale).days))
        if not 0 <= (kickoff_day-sale).days <= 2:
            raise ValueError('500开赛日超出销售日范围')
        handicap_nodes = row.cls('sp_rq') + row.cls('sp_sr')
        h = re.search(r'[+-]?\d+',handicap_nodes[0].text()) if handicap_nodes else None
        handicap = str(int(h.group())) if h else None
        number = re.search(r'周[一二三四五六日天]\d{3}', cells[0].text())
        m = new_match('500', a['fid'],target_date,number.group() if number else '',names[0],names[1],names[2],
            str(kickoff_day)+'T'+day_time.group(2),handicap,a.get('status')=='4',at,url)
        m['source_attrs'] = dict(a, adapter='500_PUBLIC_SCORE')
        m['issues'].append('500_PUBLIC_SCORE_ONLY_SPF_RQSPF')
        m['issues'].append('SALE_STATUS_NOT_PUBLISHED_BY_SCORE_PAGE')
        for source_key,play in [('sp','SPF'),('rqsp','RQSPF')]:
            values = odds.get(a['fid'],{}).get(source_key,[])
            if values and len(values)!=3:raise ValueError('500竞彩SP选项数量变化')
            for label,value in zip(['胜','平','负'],values):
                set_quote(m,play,label,str(value),None,url,at)
        if handicap is None:
            m['issues'].append('HANDICAP_MISSING')
        matches.append(finish_match(m))
    return matches, dict(status='PARSED' if matches else 'NO_ROWS_REPORTED',observed_date=actual_date,
        adapter='500_PUBLIC_SCORE',available_plays=['SPF','RQSPF'],missing_plays=['JQS','BQC','BF'])


def decode(body, content_type=''):
    # The Okooo main page is GBK; the more-play response is UTF-8.
    try:
        return body.decode('utf-8-sig')
    except UnicodeDecodeError:
        return body.decode('gb18030', errors='replace')


def text_cls(node, name):
    nodes = node.cls(name)
    return nodes[0].text() if nodes else ''


def parse_500(body, target_date, url, at):
    root = Tree(decode(body)).root
    matches, rejected = [], []
    rows = root.all(**{'data-fixtureid': None})
    for row in rows:
        a = row.attrs
        if a.get('data-processdate') != target_date:
            rejected.append(a.get('data-processdate'))
            continue
        m = new_match('500', a['data-fixtureid'], a['data-processdate'], a.get('data-matchnum', ''),
            a.get('data-simpleleague', ''), a.get('data-homesxname', ''), a.get('data-awaysxname', ''),
            a.get('data-matchdate', '') + 'T' + a.get('data-matchtime', ''), a.get('data-rangqiu'),
            a.get('data-isend') == '1', at, url)
        m['source_attrs'] = a.copy()
        m['cutoff_at'] = timestamp(a.get('data-buyendtime'))
        if m['cutoff_at'] and m['cutoff_at'] <= at:
            m['sale_status'] = 'CLOSED'
        elif m['sale_status'] != 'CLOSED' and a.get('data-isactive') == '1' and a.get('data-isend') == '0':
            m['sale_status'] = 'OPEN_OBSERVED'
        blocks = [row]
        siblings = row.parent.children
        i = siblings.index(row)
        for nxt in siblings[i + 1:]:
            if not isinstance(nxt, Node):
                continue
            if 'bet-more-wrap' in nxt.attrs.get('class', '').split():
                blocks.append(nxt)
            break
        for block in blocks:
            for n in block.all(**{'data-type': None, 'data-value': None}):
                kind = n.attrs['data-type']
                play = {'nspf':'SPF', 'spf':'RQSPF', 'bqc':'BQC', 'jqs':'JQS', 'bf':'BF'}.get(kind)
                if not play:
                    continue
                raw = n.attrs['data-value']
                if play in ('SPF', 'RQSPF'):
                    option = {'3':'胜', '1':'平', '0':'负'}.get(raw)
                elif play == 'BQC':
                    parts = raw.split('-')
                    option = '/'.join({'3':'胜', '1':'平', '0':'负'}.get(x, '?') for x in parts)
                elif play == 'JQS':
                    option = '7+' if raw == '7' else raw
                else:
                    option = raw.replace('其它', '其他')
                value_nodes = [v for v in n.all() if v.tag in ('i', 'span')]
                display = value_nodes[-1].text() if value_nodes else None
                set_quote(m, play, option, n.attrs.get('data-sp'), display, url, at)
        flags = dict(x.split(':', 1) for x in a.get('data-subactive', '').split(',') if ':' in x)
        for p, prefix in {'SPF':'nspf', 'RQSPF':'spf', 'BQC':'bq', 'JQS':'jq', 'BF':'bf'}.items():
            market = m['markets'][p]
            market['single_sale_flag'] = flags.get(prefix + 'dg')
            market['parlay_sale_flag'] = flags.get(prefix + 'gg')
            market['sale_status'] = 'CLOSED' if m['sale_status'] == 'CLOSED' else (
                'OPEN_OBSERVED' if m['sale_status'] == 'OPEN_OBSERVED' and '1' in
                (flags.get(prefix + 'dg'), flags.get(prefix + 'gg')) else 'UNKNOWN')
        matches.append(finish_match(m))
    if rejected:
        status = 'DATE_MISMATCH'
    elif matches:
        status = 'PARSED'
    elif '暂无赛事信息' in root.text():
        status = 'NO_ROWS_REPORTED'
    else:
        status = 'PARSE_FAILED'
    return matches, dict(status=status, rejected_dates=sorted(set(rejected)))


def parse_okooo(body, target_date, url, at):
    root = Tree(decode(body)).root
    date_nodes = root.all(id='ChangeDate')
    # Only the selected date label; the menu contains many other dates.
    selected = date_nodes[0].children if date_nodes else []
    label = next((n.text() for n in selected if isinstance(n, Node) and n.tag == 'a'), '')
    found = re.search(r'\d{4}-\d{2}-\d{2}', label)
    actual_date = found.group() if found else None
    if actual_date != target_date:
        return [], dict(status='DATE_MISMATCH', observed_date=actual_date)
    matches = []
    for row in root.all(**{'data-morder': None, 'data-mid': None}):
        a = row.attrs
        time_nodes = row.cls('shijian')
        tm = re.search(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}', time_nodes[0].attrs.get('title', '')) if time_nodes else None
        home_nodes = [n for n in row.all(**{'data-wf':'0', 'data-wz':'0'})]
        away_nodes = [n for n in row.all(**{'data-wf':'0', 'data-wz':'2'})]
        home = text_cls(home_nodes[0], 'zhum') if home_nodes else ''
        away = text_cls(away_nodes[0], 'zhum') if away_nodes else ''
        m = new_match('okooo', a['data-mid'], actual_date, a.get('data-ordercn', ''),
            text_cls(row, 'saiming'), home, away, tm.group() if tm else None, a.get('data-rq'),
            a.get('data-end') == '1', at, url)
        m['source_attrs'] = a.copy()
        m['match_order'] = a['data-morder']
        from results import okooo_result_main
        okooo_result_main(row,m,url,at)
        if m['sale_status'] != 'CLOSED' and a.get('data-end') == '0':
            m['sale_status'] = 'OPEN_OBSERVED'
        for n in row.all(**{'data-wf': None, 'data-wz': None}):
            play = {'0':'SPF', '1':'RQSPF'}.get(n.attrs['data-wf'])
            if play and n.attrs['data-wz'] in ('0', '1', '2'):
                option = ['胜', '平', '负'][int(n.attrs['data-wz'])]
                set_quote(m, play, option, n.attrs.get('data-sp'), text_cls(n, 'peilv'), url, at)
                if m['sale_status'] == 'OPEN_OBSERVED' and 'weiks' not in n.attrs.get('class', '').split():
                    m['markets'][play]['sale_status'] = 'OPEN_OBSERVED'
        matches.append(finish_match(m))
    return matches, dict(status='PARSED' if matches else 'NO_ROWS_REPORTED', observed_date=actual_date)


def parse_okooo_more(body, match, url, at):
    root = Tree(decode(body)).root
    from results import okooo_result_more
    okooo_result_more(root,match,url,at)
    count = 0
    for n in root.all(**{'data-wf': None, 'data-wz': None}):
        play = {'2':'BF', '3':'BQC', '4':'JQS'}.get(n.attrs['data-wf'])
        if not play:
            continue
        label = text_cls(n, 'peilv').replace('其它', '其他').replace(' ', '')
        if play == 'BF':
            label = label.replace('-', ':')
        if play == 'JQS':
            label = '7+' if label in ('总>6球', '7+', '7球以上') else label.replace('总', '').replace('球', '')
        # BQC labels, never data-wz ordering: source indexing is column-major.
        set_quote(match, play, label, n.attrs.get('data-sp'), text_cls(n, 'peilv_1'), url, at)
        count += 1
        if match['sale_status'] == 'OPEN_OBSERVED' and 'weiks' not in n.attrs.get('class', '').split():
            match['markets'][play]['sale_status'] = 'OPEN_OBSERVED'
    if not count:
        match['issues'].append('MORE_PARSE_FAILED')
    finish_match(match)
    return count
