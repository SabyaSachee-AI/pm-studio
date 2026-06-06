import requests, json, time

login = requests.post('http://localhost:8000/api/v1/auth/login',
    data={'username': 'owner@pmstudio.com', 'password': 'password123'})
token = login.json()['access_token']
headers = {'Authorization': f'Bearer {token}'}

response = requests.post(
    'http://localhost:8000/api/v1/prds/generate',
    headers=headers,
    json={
        'project_id': 'e891ce0a-7b5a-47fb-bafd-dd9bbf728ce6',
        'requirement_id': 'c8825af9-c19a-49de-aec4-3d0b2ab22e8b'
    }
)
print('Generate:', json.dumps(response.json(), indent=2))
prd_id = response.json()['prd_id']
task_id = response.json()['task_id']

print('Waiting for PRD generation...')
for i in range(24):
    r = requests.get(f'http://localhost:8000/api/v1/tasks/{task_id}')
    status = r.json()['status']
    print(f'Attempt {i+1}: {status}')
    if status in ['SUCCESS', 'FAILURE']:
        break
    time.sleep(5)

r2 = requests.get(f'http://localhost:8000/api/v1/prds/{prd_id}', headers=headers)
prd = r2.json()
print('PRD status:', prd['status'])
if prd.get('content_json'):
    print('Executive summary:', prd['content_json']['executive_summary'][:200])
    print('Features count:', len(prd['content_json']['features']))
    print('User stories count:', len(prd['content_json']['user_stories']))
