import requests, json, time

login = requests.post('http://localhost:8000/api/v1/auth/login',
    data={'username': 'owner@pmstudio.com', 'password': 'password123'})
token = login.json()['access_token']
headers = {'Authorization': f'Bearer {token}'}

response = requests.post(
    'http://localhost:8000/api/v1/srs/generate',
    headers=headers,
    json={
        'project_id': 'e891ce0a-7b5a-47fb-bafd-dd9bbf728ce6',
        'prd_id': '04f26973-d38e-4333-bed7-c02374c4dcf9'
    }
)
print('Generate:', json.dumps(response.json(), indent=2))
srs_id = response.json()['srs_id']
task_id = response.json()['task_id']

print('Waiting for SRS generation (up to 15 minutes)...')
for i in range(90):
    r = requests.get(f'http://localhost:8000/api/v1/tasks/{task_id}')
    status = r.json()['status']
    print('Attempt ' + str(i+1) + ': ' + status)
    if status in ['SUCCESS', 'FAILURE']:
        break
    time.sleep(10)

r2 = requests.get(f'http://localhost:8000/api/v1/srs/{srs_id}', headers=headers)
srs = r2.json()
print('SRS status:', srs['status'])
if srs.get('content_json'):
    content = srs['content_json']
    frs = content.get('functional_requirements', [])
    nfrs = content.get('nonfunctional_requirements', [])
    print('FR count:', len(frs))
    print('NFR count:', len(nfrs))
    if frs:
        print('First FR:', frs[0]['fr_number'], '-', frs[0]['title'])
    if nfrs:
        print('First NFR:', nfrs[0]['category'], '-', nfrs[0]['threshold'])
else:
    print('No content - still rejected')
