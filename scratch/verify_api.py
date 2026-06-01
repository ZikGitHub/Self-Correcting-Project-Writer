import requests
import json

try:
    # 1. Get projects
    r = requests.get("http://localhost:8000/projects")
    projects = r.json().get("projects", [])
    print(f"Projects found: {projects}")
    
    if projects:
        # 2. Get files for the first project
        p = projects[0]
        print(f"\nFetching files for project: {p}")
        r = requests.get(f"http://localhost:8000/files?project={p}")
        data = r.json()
        print(f"Keys in response: {list(data.keys())}")
        if "tree" in data:
            print("\nTree structure (first 2 items):")
            print(json.dumps(data["tree"][:2], indent=2))
        else:
            print("\n'tree' key missing from response!")
            if "files" in data:
                print(f"Found 'files' key instead: {data['files'][:5]}")
except Exception as e:
    print(f"Error: {e}")
