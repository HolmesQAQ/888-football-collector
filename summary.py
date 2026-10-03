"""Compact display only. Original source identities and evidence are never merged."""
import csv
from collections import defaultdict
from model import OUTCOMES, compare


def value_text(value):
    if value is None or value == '': return '未取得'
    if isinstance(value,list): return ':'.join(map(str,value))
    return str(value)


def shared(items, getter):
    values=[getter(m) for m in items]
    if all(v==values[0] for v in values): return value_text(values[0])
    # Missing on one source is not agreement. Keep provenance for complementary fields.
    return ' / '.join(m['source']+'='+value_text(v) for m,v in zip(items,values))


def compact_rows(report):
    groups=defaultdict(list)
    for m in report['matches']:
        key=tuple(m.get(k) for k in ('sale_date','match_no','kickoff_at'))
        if not all(key): key=key+(m['source'],m['source_match_id'])
        groups[key].append(m)
    links=report.get('comparisons') or compare(report['matches'])
    matched={(c['source_500'],c['source_okooo']) for c in links if c['identity_status']=='MATCHED'}
    rows=[]
    for group in groups.values():
        # Ambiguous numbers within a source are never grouped.
        batches=[group] if len(group)==2 and {m['source'] for m in group}=={'500','okooo'} else [[m] for m in group]
        for items in batches:
            ids={m['source']:m['source_match_id'] for m in items}
            confirmed=(ids.get('500'),ids.get('okooo')) in matched
            status='单来源' if len(items)==1 else '同场已匹配' if confirmed else '候选对照：名称待核对'
            row={'销售日':items[0]['sale_date'],'编号':items[0]['match_no'],'赛事':shared(items,lambda m:m['league']),
                '开赛时间':items[0]['kickoff_at'],'来源':'+'.join(ids),'身份核对':status,
                '主队':shared(items,lambda m:m['home_team']),'客队':shared(items,lambda m:m['away_team']),
                '让球':shared(items,lambda m:m.get('handicap')),
                '销售状态':shared(items,lambda m:m.get('sale_status')),
                '比赛状态':shared(items,lambda m:m.get('result',{}).get('status')),
                '半场比分':shared(items,lambda m:m.get('result',{}).get('halftime')),
                '90分钟比分':shared(items,lambda m:m.get('result',{}).get('fulltime_90'))}
            for p in OUTCOMES:
                row['赛果_'+p]=shared(items,lambda m,p=p:m.get('result',{}).get('actual_events',{}).get(p))
            differences=0
            for p,options in OUTCOMES.items():
                for option in options:
                    def quote(m):
                        q=m['markets'][p]['options'][option]
                        return q['value'] if q['value'] is not None else q['status']
                    row[p+'_'+option]=shared(items,quote)
                    if len({quote(m) for m in items})>1:differences+=1
            row['赔率差异项数']=differences
            row['来源记录']=' / '.join(m['source']+':'+m['source_match_id'] for m in items)
            row['证据链接']=' / '.join(m['source']+'='+m['source_url'] for m in items)
            rows.append(row)
    return rows


def summary_lines(report, rows=None):
    rows=compact_rows(report) if rows is None else rows
    lines=['销售日：'+report['sale_date'],'原始来源记录：'+str(len(report['matches']))+'；汇总/对照行：'+str(len(rows)),
        '相同数值只显示一次；不一致或单站缺失时显示来源。候选对照不是同场身份确认；未做独立官方核验。','']
    for r in rows:
        lines.append(f"{r['编号']} {r['赛事']} | {r['主队']} vs {r['客队']}")
        lines.append(f"  {r['来源']} | {r['身份核对']} | 90分钟 {r['90分钟比分']} | 半场 {r['半场比分']} | 赔率差异 {r['赔率差异项数']} 项")
        lines.append('  赛果：'+'；'.join(p+' '+r['赛果_'+p] for p in OUTCOMES))
    return lines


def export_summary(folder, report):
    rows=compact_rows(report)
    with (folder/'汇总.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]) if rows else ['销售日','编号','来源'])
        writer.writeheader();writer.writerows(rows)
    (folder/'先看这里.txt').write_text('\n'.join(summary_lines(report,rows))+'\n\n完整五玩法赔率见 汇总.csv；原始分站记录和证据仍完整保留。\n',encoding='utf-8-sig')
