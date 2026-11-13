"""Start the AetherOS web server: python serve.py  ->  http://127.0.0.1:8000"""
import logging

import bootstrap
import config
from api.server import create_app


def main():
    config.ensure_dirs()
    logging.basicConfig(filename=config.LOG_PATH, level=logging.INFO,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")
    if bootstrap.api_key_missing():
        raise SystemExit("OPENAI_API_KEY is missing. Copy .env.example to .env and set it.")
    if config.API_HOST not in ("127.0.0.1", "localhost") and not config.API_TOKEN:
        raise SystemExit("Refusing to listen on a non-local address without AETHER_API_TOKEN set.")

    system = bootstrap.build_system()
    app = create_app(system, token=config.API_TOKEN)
    print(f"AetherOS web UI: http://{config.API_HOST}:{config.API_PORT}"
          + ("  (token required for /api)" if config.API_TOKEN else ""))
    try:
        app.run(host=config.API_HOST, port=config.API_PORT, threaded=True)
    finally:
        system.daemon.stop()


if __name__ == "__main__":
    main()
