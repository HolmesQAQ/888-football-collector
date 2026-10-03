"""Compact AI export; full evidence remains in snapshot.json and raw/."""
def ai_matches(matches):
    output=[]
    for m in matches:
        item={k:m.get(k) for k in ('source','source_match_id','sale_date','match_no','league','home_team','away_team','kickoff_at','handicap','source_url','collected_at','result','issues','coverage_draft')}
        item['markets']={p:dict(data_status=v['data_status'],options={k:dict(value=q['value'],status=q['status'],source_url=q['source_url'],collected_at=q['collected_at'],quoted_at=q['quoted_at']) for k,q in v['options'].items()}) for p,v in m['markets'].items()}
        facts=m.get('team_evidence',{})
        item['team_evidence']={k:v for k,v in facts.items() if k!='teams'}
        item['team_evidence']['teams']={}
        for role,t in facts.get('teams',{}).items():
            compact={k:v for k,v in t.items() if k not in ('records','recent_3','recent_5','recent_10','home_records','away_records','h2h_records')}
            for group in ('recent_3','recent_5','recent_10','home_records','away_records','h2h_records'):
                compact[group+'_ids']=[r['source_match_id'] for r in t[group]]
            compact['empty_h2h_means']='No matching record in this page window; not proof of no prior meetings.'
            item['team_evidence']['teams'][role]=compact
        output.append(item)
    return output
