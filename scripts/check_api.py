#!/usr/bin/env python3
import json
import sys
from urllib.request import urlopen

URL = 'http://127.0.0.1:5000/api/jobs/active/report?top_n=20&has_driver_license=true'

def main():
    try:
        with urlopen(URL) as r:
            data = json.load(r)
    except Exception as e:
        print('ERROR', e)
        sys.exit(2)
    tc = data.get('top_candidates', [])
    print('TOP_CANDIDATES_COUNT', len(tc))
    print('SAMPLE_FIRST_3')
    for c in tc[:3]:
        print({
            'Name': c.get('Name'),
            'Match Score (%)': c.get('Match Score (%)'),
            'Final Score (%)': c.get('Final Score (%)'),
            "Has Driver's License": c.get("Has Driver's License"),
        })

if __name__ == '__main__':
    main()
