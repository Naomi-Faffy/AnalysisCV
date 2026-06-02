import importlib
import traceback

try:
    print('Importing app...')
    m = importlib.import_module('app')
    print('App imported. Gathering routes...')
    rules = [str(rule) for rule in m.app.url_map.iter_rules()]
    if not rules:
        print('No routes found.')
    else:
        for r in sorted(rules):
            print(r)
except Exception as exc:
    print('Error while listing routes:')
    traceback.print_exc()
