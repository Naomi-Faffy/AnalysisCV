import re
import requests

s = requests.Session()
r = s.get('http://127.0.0.1:5000/login')
print('GET', r.status_code)
print('COOKIE', s.cookies.get_dict())
m = re.search(r'name="csrf_token" value="([^"]+)"', r.text)
print('CSRF', bool(m))
if not m:
    raise SystemExit('No CSRF token found')
p = s.post(
    'http://127.0.0.1:5000/login',
    data={'username': 'admin_user', 'password': 'StrongLocalPassw0rd!', 'csrf_token': m.group(1)},
    allow_redirects=False,
)
print('POST', p.status_code)
print('LOCATION', p.headers.get('Location'))
print('COOKIES', s.cookies.get_dict())
