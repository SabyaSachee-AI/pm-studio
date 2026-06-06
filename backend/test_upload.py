import requests, json, time

login = requests.post('http://localhost:8000/api/v1/auth/login',
    data={'username': 'owner@pmstudio.com', 'password': 'password123'})
token = login.json()['access_token']

with open('test_req.pdf', 'rb') as f:
    response = requests.post(
        'http://localhost:8000/api/v1/requirements/upload',
        headers={'Authorization': f'Bearer {token}'},
        data={'project_id': 'e891ce0a-7b5a-47fb-bafd-dd9bbf728ce6'},
        files={'file': ('test_req.pdf', f, 'application/pdf')}
    )
print('Upload:', json.dumps(response.json(), indent=2))
task_id = response.json()['task_id']
req_id = response.json()['requirement_id']

print('Waiting for analysis...')
for i in range(20):
    r = requests.get(f'http://localhost:8000/api/v1/tasks/{task_id}')
    status = r.json()['status']
    print(f'Attempt {i+1}: {status}')
    if status in ['SUCCESS', 'FAILURE']:
        print(json.dumps(r.json(), indent=2))
        break
    time.sleep(5)

r2 = requests.get(f'http://localhost:8000/api/v1/requirements/{req_id}',
    headers={'Authorization': f'Bearer {token}'})
print('Requirement final:', json.dumps(r2.json(), indent=2))
