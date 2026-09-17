import json
import os
from pathlib import Path

OUTPUT_PATH = Path("openapi.json")

# create_app() requires these; schema generation never opens a DB connection,
# so placeholders (as tests/conftest.py's _fake_settings fixture uses) suffice.
_FAKE_SETTINGS_ENV = {
    "AUTH__JWT_SECRET_KEY": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
    "AUTH__HMAC_SECRET_KEY": "BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB=",
    "DB__MONGODB_URL": "mongodb://localhost:27017/",
    "DB__MONGODB_DB_NAME": "canterlot_openapi",
    "DB__REDIS_URL": "redis://localhost:6379/0",
}


def main() -> None:
    for key, value in _FAKE_SETTINGS_ENV.items():
        os.environ.setdefault(key, value)

    from canterlot.app import create_app, custom_openapi

    schema = custom_openapi(create_app())
    OUTPUT_PATH.write_text(json.dumps(schema, indent=2) + "\n")


if __name__ == "__main__":
    main()
