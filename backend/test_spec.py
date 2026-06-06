import requests, json, time

TASK_ID = '7923c462-f2e2-4802-8569-cd26ff3c13bf'

login = requests.post('http://localhost:8000/api/v1/auth/login',
    data={'username': 'owner@pmstudio.com', 'password': 'password123'})
token = login.json()['access_token']
headers = {'Authorization': f'Bearer {token}'}

response = requests.post(
    'http://localhost:8000/api/v1/specs/generate',
    headers=headers,
    json={'task_id': TASK_ID}
)
print('Generate:', json.dumps(response.json(), indent=2))

if response.status_code == 202:
    spec_id = response.json()['spec_id']
else:
    spec_id = requests.get(
        f'http://localhost:8000/api/v1/specs/task/{TASK_ID}',
        headers=headers
    ).json()['id']
    print('Using existing spec_id:', spec_id)

print('Waiting for spec generation (up to 10 minutes)...')
spec = {}
for i in range(60):
    r = requests.get(f'http://localhost:8000/api/v1/specs/{spec_id}', headers=headers)
    spec = r.json()
    status = spec.get('status', 'unknown')
    print('Attempt ' + str(i+1) + ': ' + status)
    if status in ['ready', 'failed']:
        break
    time.sleep(10)

print('Spec status:', spec.get('status'))
if spec.get('content_json'):
    content = spec['content_json']
    print('Task scope:', content.get('task_scope', '')[:200])
    print('Files to modify:', len(content.get('files_to_modify', [])))
    print('Security reqs:', len(content.get('security_requirements', [])))
    print('Test reqs:', len(content.get('test_requirements', [])))
    print('Manual checklist:', len(content.get('manual_test_checklist', [])))
    if content.get('files_to_modify'):
        print('First file:', content['files_to_modify'][0])
else:
    print('No content_json yet')
