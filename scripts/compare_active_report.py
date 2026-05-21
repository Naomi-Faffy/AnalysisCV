#!/usr/bin/env python3
import requests

URLS = [
    'http://127.0.0.1:5000/api/jobs/active/report?top_n=20',
    'http://127.0.0.1:5000/api/jobs/active/report?top_n=20&has_driver_license=true',
    'http://127.0.0.1:5000/api/jobs/active/report?top_n=20&education_level=Degree',
]


def main():
    for url in URLS:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()
        top_candidates = data.get('top_candidates', [])
        license_true = sum(
            str(candidate.get("Has Driver's License", '')).strip().lower() in {'1', 'true', 'yes'}
            for candidate in top_candidates
        )
        degree_count = sum(
            'degree' in str(candidate.get('Education Level', '')).strip().lower()
            for candidate in top_candidates
        )
        print('URL', url)
        print('COUNT', len(top_candidates), 'LICENSE_TRUE', license_true, 'DEGREE_COUNT', degree_count)
        print('FIRST_3', [
            (
                candidate.get('Name'),
                candidate.get("Has Driver's License"),
                candidate.get('Education Level'),
                candidate.get('Final Score (%)'),
            )
            for candidate in top_candidates[:3]
        ])
        print('---')


if __name__ == '__main__':
    main()
