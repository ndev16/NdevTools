# -*- coding: utf-8 -*-
"""Human-readable wall trace ledger, shared by the ribbon and offline investigation."""
from collections import Counter
from ndev_main_cad_wall_plan import wall_plan, run_key


def trace_report(rows,choices,lines,diagnostics,exclude,cutoff,details,outcomes=None,
                 unmatched=(),failed=None,labels=None,min_run=1.0/304.8):
    pieces=[]
    wall_plan(rows,choices,exclude,cutoff,pieces,min_run)
    text=['CAD WALL TRACE REPORT',details,'XY coordinates: Revit internal feet; widths: inches.',
          'Source faces are numbered within this scan. Candidates are hypotheses, not a count of physical walls.']
    if failed:
        text.append('Placement stopped: '+failed)
    orphan=[]
    def xy(axis):
        return '({:.3f}, {:.3f}) to ({:.3f}, {:.3f})'.format(axis[0][0],axis[0][1],axis[1][0],axis[1][1])
    for row in rows:
        key=row['key']
        records=[]
        tally=Counter()
        for owner,p,state in pieces:
            if owner is not row:
                continue
            if state=='no mapping':
                state='no loaded matching width' if key in unmatched else 'mapped to None'
            if state=='eligible':
                state=(outcomes or {}).get(run_key(p),('not committed' if failed else 'eligible; not placed',None))[0]
            element=(outcomes or {}).get(run_key(p),('',None))[1]
            tally[state.split(' with faces')[0].split(';')[0]]+=1
            records.append('  {} | faces {} | {}{}'.format(state,p['faces'],xy(p['axis']),
                           ' | Revit ID '+str(element) if element is not None else ''))
        text.extend(['','{:.2f} in | {} | {}'.format(row['width_mm']/25.4,(labels or choices).get(key) or 'None',
                    ', '.join('{}: {}'.format(status,n) for status,n in sorted(tally.items())))]+records)
    for index,(a,b,layer) in enumerate(lines):
        counts=diagnostics.get(index,{})
        if not counts.get('candidate'):
            orphan.append('  face {} | {} | {} | {}'.format(index,layer,xy((a,b)),
                          ', '.join('{} ({})'.format(k,v) for k,v in sorted(counts.items()))
                          or 'no overlapping parallel straight face in the scanned layers'))
    text.extend(['','{} scanned straight faces; {} have no candidate within the scan rules.'.format(len(lines),len(orphan))]+orphan)
    return '\n'.join(text)+'\n'
