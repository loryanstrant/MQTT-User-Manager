from app import create_app

application = create_app()

if __name__ == "__main__":
    from waitress import serve

    serve(
        application,
        host="0.0.0.0",
        port=8080,
        threads=4,
        channel_timeout=30,
        connection_limit=64,
        backlog=64,
        max_request_body_size=16384,
        max_request_header_size=8192,
        expose_tracebacks=False,
    )
