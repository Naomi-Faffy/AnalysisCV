from cv_analyzer.cv_parser import CVParser

samples = {
    'normal': 'Contact: john.doe@example.com',
    'obf1': 'Email: jane [at] example (dot) com',
    'obf2': 'Contact: mark(at)sub.domain(dot)co.uk',
    'spaced': 'reach me at user at domain dot com',
    'unicode': 'send to user＠example．com',
    'label_inline': 'E-mail: admin(at)example.com, Phone: 1234'
}

p = CVParser()
for name, text in samples.items():
    email = p.extract_email(text)
    print(f"{name}: {text} -> {email}")
