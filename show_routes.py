import traceback

try:
    from app import create_app  # import application factory
    flask_app = create_app()

    rules = sorted([r.rule for r in flask_app.url_map.iter_rules()])
    print("Registered routes:")
    for r in rules:
        print(" ", r)
except Exception:
    traceback.print_exc()