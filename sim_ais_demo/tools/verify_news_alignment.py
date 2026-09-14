"""Independent two-gate crossing and post-closure acceptance for the NEW batch."""
import json
from collections import defaultdict
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]


def passages(rows):
    # Remember the last OUTSIDE side across arbitrarily many reports inside the band.
    # A single entry line is not a completed crossing.
    previous_side = None
    result = []
    for row in rows:
        lon, lat = row['longitude'], row['latitude']
        if not 25.8 <= lat <= 27.1:
            continue
        side = 'west' if lon < 56.2 else 'east' if lon > 56.7 else None
        if side is None:
            continue
        if previous_side is not None and side != previous_side:
            result.append(row['recorded_at'])
        previous_side = side
    return result


def main():
    cfg = json.loads((ROOT / 'config/news_aligned_config.json').read_text(encoding='utf-8'))
    out = ROOT / cfg['output']['directory']
    rows_by_ship = defaultdict(list)
    for path in sorted((out / 'positions_by_date').glob('*.jsonl')):
        for line in path.read_text(encoding='utf-8').splitlines():
            row = json.loads(line)
            rows_by_ship[row['temp_ship_id']].append(row)
    phases = cfg['scenario_phases']
    counts = {p['id']: 0 for p in phases}
    closure = datetime.fromisoformat(cfg['closure_policy']['announced_closure_utc'])
    post_crossings = []
    core_rows = []
    for ship, rows in rows_by_ship.items():
        rows.sort(key=lambda r: r['recorded_at'])
        for stamp in passages(rows):
            t = datetime.fromisoformat(stamp)
            for p in phases:
                if datetime.fromisoformat(p['start_utc']) <= t < datetime.fromisoformat(p['end_utc']):
                    counts[p['id']] += 1
            if t >= closure:
                post_crossings.append([ship, stamp])
        core_rows.extend([ship, r['recorded_at']] for r in rows
                         if datetime.fromisoformat(r['recorded_at']) >= closure
                         and 56.2 < r['longitude'] < 56.7 and 26.1 < r['latitude'] < 27.1)
    links = json.loads((out / 'scenario_links.json').read_text(encoding='utf-8'))
    last = {s: rows[-1] for s, rows in rows_by_ship.items()}
    internal = {s['temp_ship_id'] for s in links['participating_ships'] if s['route'].startswith('gulf_internal')}
    missing_wait = sorted(s for s, r in last.items() if s not in internal and (r['nav_status'] != '漂航' or r['speed'] >= 0.5))
    report = {
        'scope': 'Only output_news_aligned; old batch not rechecked.',
        'definition_zh': '跨越56.2与56.7两条门线才算完整穿越，保留带内多次报位之间的状态；不把跨入一条线计为过境。',
        'completed_crossings_by_phase': counts,
        'post_closure_completed_crossings': post_crossings,
        'post_closure_core_position_count': len(core_rows),
        'gulf_internal_ship_ids': sorted(internal),
        'transit_ships_not_waiting_at_last_report': missing_wait,
        'last_observation_waiting_ships': sorted(s for s,r in last.items() if r['nav_status']=='漂航' and r['speed']<0.5),
        'last_observation_underway_ships': sorted(s for s,r in last.items() if r['speed']>=0.5),
        'assumptions': cfg['closure_policy']['assumptions_zh'],
        'failures': []}
    if not counts[phases[0]['id']]:
        report['failures'].append('无事件前完整过境基线')
    if post_crossings or core_rows:
        report['failures'].append('宣告封锁后仍存在完整穿越或海峡核心区船位')
    if missing_wait:
        report['failures'].append('需要穿越海峡的船舶未持续待命')
    # Semantic check: new artifacts must not retain the legacy recovery narrative.
    if '有限复航与试探性通行' in json.dumps(links, ensure_ascii=False):
        report['failures'].append('仍有旧复航情景叙述')
    (out/'news_alignment_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return bool(report['failures'])


if __name__ == '__main__':
    raise SystemExit(main())
