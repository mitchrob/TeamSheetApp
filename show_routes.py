import traceback

try:
    import app as app_module  # import your app.py module
    flask_app = app_module.app  # the Flask() instance inside app.py

    rules = sorted([r.rule for r in flask_app.url_map.iter_rules()])
    print("Registered routes:")
    for r in rules:
        print(" ", r)
except Exception:
    traceback.print_exc()