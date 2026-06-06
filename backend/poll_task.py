import requests, json, time

login = requests.post('http://localhost:8000/api/v1/auth/login',
    data={'username': 'owner@pmstudio.com', 'password': 'password123'})
token = login.json()['access_token']

task_id = '981d6a15-b828-482a-8fcd-8401cb8dabeb'
for i in range(10):
    r = requests.get(f'http://localhost:8000/api/v1/tasks/{task_id}')
    data = r.json()
    status = data['status']
    print(f'Attempt {i+1}: status={status}')
    if status in ['SUCCESS', 'FAILURE']:
        print('Final result:', json.dumps(data, indent=2))
        break
    time.sleep(3)

req_id = 'ae9cab35-a681-49c3-b9e2-a63d59d9280b'
r2 = requests.get(f'http://localhost:8000/api/v1/requirements/{req_id}',
    headers={'Authorization': f'Bearer {token}'})
print('Requirement:', json.dumps(r2.json(), indent=2))
