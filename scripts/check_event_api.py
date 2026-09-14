"""Read-only HTTP checks for the approved 65-event / 290-news dataset."""
import argparse
import json
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', default='http://127.0.0.1:8000')
    args = parser.parse_args()

    def get(path):
        with urlopen(Request(args.base + path, headers={'Origin': 'http://localhost:5174'}), timeout=20) as response:
            assert response.status == 200
            assert response.headers['Access-Control-Allow-Origin'] == 'http://localhost:5174'
            raw = response.read()
            return json.loads(raw) if 'application/json' in response.headers['Content-Type'] else raw

    assert get('/health')['status'] == 'ok'
    assert b'swagger-ui' in get('/docs')
    events = get('/events')
    assert len(events) == 65
    assert sum(e['event_lat'] is None for e in events) == 25
    assert sum(e['event_datetime'] is None for e in events) == 38
    assert len({e['event_id'] for e in events}) == 65
    seen = set()
    for event in events:
        stories = get('/events/' + event['event_id'] + '/news')
        assert len(stories) == event['coverage_count']
        assert not any('content' in n for n in stories)
        for story in stories:
            assert story['story_id'] not in seen
            seen.add(story['story_id'])
    assert len(seen) == 223
    try:
        get('/events/evt_missing/news')
        raise AssertionError('Missing event must return 404')
    except HTTPError as error:
        assert error.code == 404
    meta = get('/simulation/meta')
    assert meta['event_count'] == 0 and meta['is_simulated'] is True
    assert (meta['ship_count'], meta['position_count'], meta['frame_count']) == (150, 14400, 96)
    assert len(get('/ships/map')) == 150
    print('PASS: health/docs/CORS, 65 events, nullable fields, 223 unique related stories, 404, separate simulation counts and 150 ships')


if __name__ == '__main__':
    main()
