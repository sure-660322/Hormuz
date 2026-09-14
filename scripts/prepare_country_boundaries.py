"""Download Natural Earth's generalized 1:50m countries; retain the requested countries only."""
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

SOURCE = 'https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_admin_0_countries.geojson'
NAMES = {'IRN': '伊朗', 'SAU': '沙特阿拉伯', 'ARE': '阿联酋', 'OMN': '阿曼',
         'IRQ': '伊拉克', 'KWT': '科威特', 'QAT': '卡塔尔', 'BHR': '巴林', 'ISR': '以色列', 'SYR': '叙利亚', 'LBN': '黎巴嫩', 'JOR': '约旦', 'PSX': '巴勒斯坦'}


def main():
    raw = urlopen(SOURCE, timeout=45).read()
    features = []
    for feature in json.loads(raw)['features']:
        p = feature['properties']
        if p['ADM0_A3'] in NAMES:
            features.append({'type': 'Feature', 'properties': {
                'code': p['ADM0_A3'], 'name_zh': NAMES[p['ADM0_A3']],
                'label': [p['LABEL_Y'], p['LABEL_X']],
            }, 'geometry': feature['geometry']})
    assert len(features) == len(NAMES)
    target = Path(__file__).resolve().parents[1] / 'frontend/public/data'
    target.mkdir(exist_ok=True)
    payload = json.dumps({'type': 'FeatureCollection', 'features': features}, ensure_ascii=False, separators=(',', ':')).encode()
    (target / 'gulf-countries.geojson').write_bytes(payload)
    (target / 'gulf-countries.source.json').write_text(json.dumps({
        'source': SOURCE, 'dataset': 'Natural Earth Admin 0 Countries 1:50m',
        'license': 'Public domain', 'terms': 'https://www.naturalearthdata.com/about/terms-of-use/',
        'source_sha256': hashlib.sha256(raw).hexdigest(), 'output_sha256': hashlib.sha256(payload).hexdigest(),
        'processing': 'Requested countries selected from already generalized 50m geometry; original rings and islands preserved.',
        'bytes': len(payload), 'countries': NAMES,
    }, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Prepared', len(features), 'countries;', len(payload), 'bytes')


if __name__ == '__main__':
    main()
