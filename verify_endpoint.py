import requests
import sys

try:
    # Need to login or rely on session? 
    # player_names is @admin_required.
    # So I need to login first.
    
    s = requests.Session()
    # Login
    r = s.post('http://127.0.0.1:5000/login', data={'username': 'admin', 'password': 'password'})
    if r.status_code != 200:
        print(f"Login failed: {r.status_code}")
        sys.exit(1)
        
    # Check player_names
    r = s.get('http://127.0.0.1:5000/player_names')
    if r.status_code != 200:
        print(f"player_names failed: {r.status_code}")
        sys.exit(1)
        
    data = r.json()
    # Expect list of {name, count}
    if not isinstance(data, list):
        print("Data is not a list")
        sys.exit(1)
        
    print(f"Received {len(data)} players.")
    
    found_milestone = False
    for p in data:
        if p['name'] == 'Milestone Test Player':
            print(f"Found Milestone Test Player with count: {p['count']}")
            if p['count'] == 49:
                found_milestone = True
                
    if found_milestone:
        print("SUCCESS: Endpoint returned correct count for test player.")
    else:
        print("FAILURE: Endpoint did not return correct count for test player.")
        
except Exception as e:
    print(f"Error: {e}")
