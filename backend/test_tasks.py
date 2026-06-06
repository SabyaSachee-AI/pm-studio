import requests, json

login = requests.post('http://localhost:8000/api/v1/auth/login',
    data={'username': 'owner@pmstudio.com', 'password': 'password123'})
token = login.json()['access_token']
headers = {'Authorization': f'Bearer {token}'}

project_id = 'e891ce0a-7b5a-47fb-bafd-dd9bbf728ce6'
srs_id = '19a6bc78-dc0a-45a6-923b-3d259ef6478b'

# Create 3 tasks
tasks_to_create = [
    {
        'project_id': project_id,
        'srs_id': srs_id,
        'title': 'Implement user registration and login',
        'task_type': 'feature',
        'priority': 'critical',
        'module_name': 'Authentication',
        'fr_references': ['FR-001', 'FR-002'],
        'effort_hours': 8.0
    },
    {
        'project_id': project_id,
        'srs_id': srs_id,
        'title': 'Build product catalog with search',
        'task_type': 'feature',
        'priority': 'high',
        'module_name': 'Catalog',
        'fr_references': ['FR-003', 'FR-004'],
        'effort_hours': 16.0
    },
    {
        'project_id': project_id,
        'srs_id': srs_id,
        'title': 'Integrate Stripe payment gateway',
        'task_type': 'feature',
        'priority': 'critical',
        'module_name': 'Payment',
        'fr_references': ['FR-005'],
        'effort_hours': 12.0
    }
]

created_ids = []
for t in tasks_to_create:
    r = requests.post('http://localhost:8000/api/v1/tasks',
        headers=headers, json=t)
    print('Created:', r.json()['title'], '- status:', r.json()['status'])
    created_ids.append(r.json()['id'])

# Move first task to in_progress
r = requests.patch(
    f'http://localhost:8000/api/v1/tasks/{created_ids[0]}/status',
    headers=headers,
    json={'status': 'in_progress', 'note': 'Starting authentication module'}
)
print('Status update:', r.json()['status'])

# Get kanban board
r = requests.get(f'http://localhost:8000/api/v1/tasks/kanban/{project_id}',
    headers=headers)
board = r.json()
print('Kanban board:')
for col, tasks in board.items():
    print(f'  {col}: {len(tasks)} tasks')
