from app import create_app

app = create_app()

if __name__ == '__main__':
    # Ensure the app binds to all network interfaces on port 3443
    app.run(host='0.0.0.0', port=3443, debug=False)
