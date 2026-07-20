import sys, json, subprocess, urllib.request

ENV = {}
for line in open('/home/dxbx/tutordog/.env'):
    line = line.strip()
    if '=' in line and not line.startswith('#'):
        k, v = line.split('=', 1)
        ENV[k] = v.strip().strip('"')
TOKEN = ENV['PACHCA_TOKEN']
PW = ENV['REDIS_PASSWORD']


def rget(k):
    out = subprocess.run(['docker', 'exec', 'tutordog_redis', 'redis-cli', '-a', PW, '--no-auth-warning', 'GET', k],
                         capture_output=True, text=True)
    return out.stdout.strip()


def rset(k, v):
    p = subprocess.run(['docker', 'exec', '-i', 'tutordog_redis', 'redis-cli', '-a', PW, '--no-auth-warning', '-x', 'SET', k],
                       input=v, capture_output=True, text=True)
    return p.stdout.strip()


def pachca(body):
    req = urllib.request.Request('https://api.pachca.com/api/shared/v1/messages',
                                 data=json.dumps(body).encode('utf-8'), method='POST',
                                 headers={'Authorization': 'Bearer ' + TOKEN, 'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


for sid in sys.argv[1:]:
    raw = rget(sid)
    if raw.startswith('='):
        raw = raw[1:]
    s = json.loads(raw)
    if s.get('статус') != 'в процессе':
        s['статус'] = 'в процессе'
    qids = [x.strip() for x in s['question_ids'].split(',')]
    idx = int(s['current_question_index'])
    q = json.loads(s['questions_data'])[qids[idx]]
    n = idx + 1
    total = s['total_questions']
    content = f"📋 Вопрос {n} из {total}\n\n{q['текст_вопроса']}\n\nВыбери один вариант ответа:"
    buttons = [
        [{"text": q['вариант_A'], "data": "A"}],
        [{"text": q['вариант_B'], "data": "B"}],
        [{"text": q['вариант_C'], "data": "C"}],
        [{"text": q['вариант_D'], "data": "D"}],
    ]
    body = {"message": {"entity_type": "user", "entity_id": int(s['pachca_user_id']), "content": content, "buttons": buttons}}
    resp = pachca(body)
    mid = resp['data']['id']
    s['last_message_id'] = mid
    rset(sid, json.dumps(s, ensure_ascii=False))
    print(f"{sid} | {s['ФИО']} | pid={s['pachca_user_id']} | resent Q{n}/{total} | new last_message_id={mid}")
